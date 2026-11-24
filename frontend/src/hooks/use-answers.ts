import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import api from '../lib/api';
import {useAuthStore} from '../stores/auth-store';

export type AnswerCategory = 'contact' | 'work_auth' | 'experience' | 'compensation' | 'availability' | 'eeo' | 'custom';

export interface SavedAnswer {
  id?: string;
  question: string;
  answer: string;
  category: AnswerCategory;
  sensitive: boolean;
}

export function useAnswers() {
  return useQuery<SavedAnswer[]>({
    queryKey: ['answers'],
    queryFn: async () => (await api.get<{ answers: SavedAnswer[] }>('/answers/')).answers,
    retry: false,
  });
}

export function useSaveAnswers() {
  const owner=useAuthStore(s=>s.user?.id);
  const queryClient = useQueryClient();
  return useMutation<SavedAnswer[], Error, SavedAnswer[]>({
    mutationFn: async (answers) => (await api.put<{ answers: SavedAnswer[] }>('/answers/', { answers },{expectedUserId:owner})).answers,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['answers'] }),
  });
}

export function useDeleteAnswer() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (id) => api.delete<void>(`/answers/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['answers'] }),
  });
}
