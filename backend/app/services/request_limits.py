"""Bound upload request bodies before Starlette parses/spools multipart parts."""
import tempfile

from starlette.responses import JSONResponse


class UploadBodyLimitMiddleware:
    LIMITS = {
        "/api/v1/resume/upload": 11 * 1024 * 1024,
        "/api/v1/network/import": 201 * 1024 * 1024,
    }

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        limit = self.LIMITS.get(scope.get("path", ""))
        if scope["type"] != "http" or scope.get("method") != "POST" or not limit:
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        length = headers.get(b"content-length")
        if length and (not length.isdigit() or int(length) > limit):
            return await JSONResponse({"detail": "Upload request exceeds the supported size."}, status_code=413)(scope, receive, send)
        # A bounded spool handles chunked requests too, before multipart parsing.
        with tempfile.SpooledTemporaryFile(max_size=1024 * 1024) as spool:
            total = 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                total += len(chunk)
                if total > limit:
                    return await JSONResponse({"detail": "Upload request exceeds the supported size."}, status_code=413)(scope, receive, send)
                spool.write(chunk)
                if not message.get("more_body", False):
                    break
            spool.seek(0)
            finished = False

            async def bounded_receive():
                nonlocal finished
                if finished:
                    return await receive()
                chunk = spool.read(64 * 1024)
                finished = spool.tell() == total
                return {"type": "http.request", "body": chunk, "more_body": not finished}

            await self.app(scope, bounded_receive, send)
