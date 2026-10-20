import { useState } from 'react';

/**
 * Local editable copy of a server value.
 * The draft re-syncs only when the server value actually changes (compared
 * by value), so background refetches don't wipe in-progress edits.
 */
export function useDraft<T>(source: T) {
  const [draft, setDraft] = useState<T>(source);
  const [synced, setSynced] = useState<string>(() => JSON.stringify(source));

  const serialized = JSON.stringify(source);
  if (serialized !== synced) {
    setSynced(serialized);
    setDraft(source);
  }

  const dirty = JSON.stringify(draft) !== serialized;
  const reset = () => setDraft(source);
  return { draft, setDraft, dirty, reset };
}
