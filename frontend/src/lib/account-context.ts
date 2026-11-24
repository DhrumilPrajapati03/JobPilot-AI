// Requests must retain the account they began in, including an A -> B -> A switch.
let account: string | null | undefined;
let revision = 0;
export const accountContext = () => ({account, revision});
export function setAccountContext(next: string | null) {
  if (account !== next) { account = next; revision++; }
}
