import { ref, type Ref } from "vue";
import { ElMessage } from "element-plus";

interface UseAsyncReturn<T> {
  data: Ref<T | null>;
  loading: Ref<boolean>;
  error: Ref<string | null>;
  execute: (...args: unknown[]) => Promise<T | null>;
  reset: () => void;
}

export function useAsync<T>(
  fn: (...args: unknown[]) => Promise<T>,
  options: {
    immediate?: boolean;
    showError?: boolean;
    errorMessage?: string;
    onSuccess?: (data: T) => void;
    onError?: (err: Error) => void;
  } = {}
): UseAsyncReturn<T> {
  const { showError = true, errorMessage, onSuccess, onError } = options;

  const data = ref<T | null>(null) as Ref<T | null>;
  const loading = ref(false);
  const error = ref<string | null>(null);

  const execute = async (...args: unknown[]): Promise<T | null> => {
    loading.value = true;
    error.value = null;
    try {
      const result = await fn(...args);
      data.value = result;
      onSuccess?.(result);
      return result;
    } catch (err: unknown) {
      const msg =
        errorMessage ||
        (err instanceof Error ? err.message : "操作失败，请稍后重试");
      error.value = msg;
      if (showError) {
        ElMessage.error({ message: msg, grouping: true });
      }
      onError?.(err instanceof Error ? err : new Error(msg));
      return null;
    } finally {
      loading.value = false;
    }
  };

  const reset = () => {
    data.value = null;
    loading.value = false;
    error.value = null;
  };

  return { data, loading, error, execute, reset };
}
