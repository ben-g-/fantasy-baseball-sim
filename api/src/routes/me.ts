import { Request, Response, Router } from 'express';
import { requireAuth, AuthenticatedRequest } from '../middleware/auth';
import { supabase } from '../lib/supabase';
import { apiError } from '../lib/errors';

export const meRouter = Router();

meRouter.get('/me', requireAuth, async (req: Request, res: Response): Promise<void> => {
  const { userId } = req as AuthenticatedRequest;

  const { data: profile, error } = await supabase
    .from('profiles')
    .select('id, display_name')
    .eq('id', userId)
    .single();

  if (error || !profile) {
    res.status(404).json(apiError('not_found', 'Profile not found'));
    return;
  }

  res.json(profile);
});
