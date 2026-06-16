import { Request, Response, Router } from 'express';
import { requireAuth, AuthenticatedRequest } from '../middleware/auth';
import { supabase } from '../lib/supabase';

export const meRouter = Router();

meRouter.get('/me', requireAuth, async (req: Request, res: Response): Promise<void> => {
  const { userId } = req as AuthenticatedRequest;

  const { data: profile, error } = await supabase
    .from('profiles')
    .select('id, username, display_name')
    .eq('id', userId)
    .single();

  if (error || !profile) {
    res.status(404).json({ error: 'Profile not found' });
    return;
  }

  res.json(profile);
});
