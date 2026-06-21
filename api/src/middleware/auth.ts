import { Request, Response, NextFunction } from 'express';
import { supabase } from '../lib/supabase';
import { apiError } from '../lib/errors';

export interface AuthenticatedRequest extends Request {
  userId: string;
}

export async function requireAuth(
  req: Request,
  res: Response,
  next: NextFunction,
): Promise<void> {
  const authHeader = req.headers.authorization;
  if (!authHeader?.startsWith('Bearer ')) {
    res.status(401).json(apiError('unauthorized', 'Missing or invalid authorization header'));
    return;
  }

  const token = authHeader.slice(7);
  const {
    data: { user },
    error,
  } = await supabase.auth.getUser(token);

  if (error || !user) {
    res.status(401).json(apiError('unauthorized', 'Invalid or expired token'));
    return;
  }

  (req as AuthenticatedRequest).userId = user.id;
  next();
}
