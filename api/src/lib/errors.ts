export type ErrorCode =
  | 'unauthorized'
  | 'forbidden'
  | 'not_found'
  | 'conflict'
  | 'validation_error'
  | 'server_error';

export function apiError(code: ErrorCode, message: string) {
  return { error: { code, message } };
}
