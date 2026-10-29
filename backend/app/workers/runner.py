"""Run with: python -m app.workers.runner [--once].

PostgreSQL is the durable queue. A separate heartbeat thread renews the lease
even while a synchronous PDF/parser operation occupies the asyncio event loop.
"""
import argparse
import asyncio
import logging
import signal
import threading
import uuid
from datetime import datetime, timezone

from app.config import settings
from app.services import autopilot, digest, discovery
from app.services.runs import LeaseLost, PermanentRunError, RunStore, current_execution, durable_enabled
from app.workflows.application import run_application
from app.workflows.context import ExecutionContext
from app.services.observability import setup_monitoring, capture_error

log = logging.getLogger(__name__)


class Worker:
    def __init__(self, store=None, heartbeat_factory=RunStore):
        self.store = store or RunStore()
        self.heartbeat_factory = heartbeat_factory
        self.id = str(uuid.uuid4())
        self.last_poll = None
        self.active_run_id = None

    async def run_once(self):
        run = await asyncio.to_thread(self.store.claim, self.id)
        self.last_poll = datetime.now(timezone.utc).isoformat()
        if not run:
            return False
        self.active_run_id = run['id']
        stop, lost = threading.Event(), threading.Event()

        def heartbeat():
            try:
                repo = self.heartbeat_factory()
            except Exception:
                lost.set()
                return
            while not stop.wait(max(5, settings.RUN_LEASE_SECONDS / 3)):
                try:
                    if not repo.renew(run["id"], run["lease_token"]):
                        lost.set()
                        return
                except Exception:
                    lost.set()  # Fail closed; expiry allows another worker to recover.
                    return

        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        ctx = ExecutionContext(self.store, run, lost)
        binding = current_execution.set(ctx)
        try:
            result = await self.execute(ctx)
            ctx.check()
            await asyncio.to_thread(self.store.finish, run["id"], ctx.token, "succeeded", result=result)
        except asyncio.CancelledError:
            # Leave the claimed row for lease-expiry recovery; no false success.
            raise
        except Exception as exc:
            if isinstance(exc, LeaseLost) or "lease_lost" in str(exc) or lost.is_set():
                log.warning("Lease lost for run %s; this worker will not commit", run["id"])
            else:
                capture_error(exc)
                terminal = isinstance(exc, PermanentRunError) or run["attempts"] >= run["max_attempts"]
                message = str(exc) if isinstance(exc, PermanentRunError) else f"{type(exc).__name__}: background stage failed"
                await asyncio.to_thread(self.store.finish, run["id"], ctx.token, "failed" if terminal else "retry_wait",
                                        error=message[:500], delay=min(300, 15 * 2 ** (run["attempts"] - 1)))
        finally:
            self.active_run_id = None
            current_execution.reset(binding)
            stop.set()
            thread.join(timeout=1)
        return True

    async def execute(self, ctx):
        db, uid = self.store.client, ctx.run["user_id"]
        email = autopilot.account_email(db, uid)
        kind = ctx.run["kind"]
        if kind in {"mail_send", "mail_sync"}:
            from app.services import mailbox
            return await (mailbox.execute_send(ctx) if kind == "mail_send" else mailbox.execute_sync(ctx))
        if kind == "application":
            return await run_application(ctx, email)
        if kind == "scan":
            async def scan():
                return await discovery.scan_user(db, uid, auto_draft=ctx.run["inputs"].get("auto_draft", True),
                                                 source_ids=ctx.run["inputs"].get("source_ids"), user_email=email)
            return await ctx.stage("scan", "Scanning followed job boards", scan)
        if kind == "digest":
            prefs = discovery.load_preferences(db, uid)
            if ctx.run["inputs"].get("scheduled_on") and not prefs.digest_enabled:
                return {"skipped": "Digest was disabled before delivery"}
            if ctx.run["inputs"].get("scheduled_on", "9999") < autopilot.local_now(prefs).date().isoformat():
                return {"skipped": "Scheduled digest is out of date"}
            # Retry against the same rendered message and recipient. Never rebuild
            # a changed email under a provider idempotency key.
            async def render():
                subject, html, text = digest.render_digest(digest.build_digest_data(db, uid, prefs))
                return {"to": prefs.digest_email or email, "subject": subject, "html": html, "text": text,
                        "from": settings.DIGEST_FROM, "prepared_at": datetime.now(timezone.utc).isoformat()}
            package = await ctx.stage("digest_package", "Preparing the morning digest", render)
            async def deliver():
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(package["prepared_at"])).total_seconds()
                if age > 23 * 3600:
                    raise PermanentRunError("Digest retry window expired. Delivery requires a new deliberate request.")
                await digest.send_email(package["to"], package["subject"], package["html"], package["text"],
                                        idempotency_key=f"jobpilot-digest/{ctx.run['id']}", sender=package["from"])
                return {"to": package["to"], "subject": package["subject"]}
            return await ctx.stage("digest_delivery", "Sending the morning digest", deliver)
        raise PermanentRunError("Unsupported job kind")


async def main(once=False):
    if not durable_enabled():
        raise SystemExit("Set EXECUTION_MODE=durable before starting the background worker.")
    if not autopilot.server_ready():
        raise SystemExit("Configure SUPABASE_URL and SUPABASE_SERVICE_KEY before starting a durable worker.")
    worker = Worker()
    setup_monitoring()
    last_schedule = 0.0
    stopped = threading.Event()
    for event in (signal.SIGINT, signal.SIGTERM):
        signal.signal(event, lambda *_: stopped.set())
    def report_health():
        try:
            repo = RunStore()
            while not stopped.is_set():
                try:
                    repo.rpc('heartbeat_execution_worker',p_worker=worker.id,p_last_poll=worker.last_poll,p_active_run=worker.active_run_id)
                except Exception:
                    log.warning('Worker health announcement unavailable; readiness may fail')
                stopped.wait(15)
        except Exception:
            log.warning('Worker health client unavailable')
    reporter = threading.Thread(target=report_health,daemon=True)
    reporter.start()
    try:
        while not stopped.is_set():
            try:
                if not once and asyncio.get_running_loop().time() - last_schedule >= autopilot.TICK_SECONDS:
                    if settings.DISCOVERY_AUTO_SCAN:
                        await autopilot.tick(worker.store.client)
                    from app.services import mailbox
                    await mailbox.schedule_sync(worker.store.client)
                    last_schedule = asyncio.get_running_loop().time()
                worked = await worker.run_once()
                if once:
                    break
                if not worked:
                    await asyncio.sleep(settings.RUN_POLL_SECONDS)
            except Exception as exc:
                log.error("Worker poll failed (%s); retrying after backoff", type(exc).__name__)
                if once:
                    raise
                await asyncio.sleep(5)
    finally:
        stopped.set()
        reporter.join(timeout=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main(args.once))
