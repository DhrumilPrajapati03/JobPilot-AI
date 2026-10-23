import { QueryClient } from '@tanstack/react-query';

const createClient = () => new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1 } },
});

export let queryClient = createClient();

export function resetQueryAccount() {
  void queryClient.cancelQueries();
  queryClient.clear();
  // In-flight mutation callbacks retain their OLD client. They cannot repopulate
  // the new account's cache even when their network response arrives late.
  queryClient = createClient();
}
