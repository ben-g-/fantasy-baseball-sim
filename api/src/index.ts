import 'dotenv/config';
import express from 'express';
import cors from 'cors';
import { meRouter } from './routes/me';
import { matchupsRouter } from './routes/matchups';
import { lineupsRouter } from './routes/lineups';
import { devRouter } from './routes/dev';
import { startSimDispatcher } from './lib/simDispatcher';

const app = express();
const port = process.env.PORT ?? 3000;

app.use(cors({ origin: process.env.CORS_ORIGIN ?? '*' }));
app.use(express.json());

app.use('/api/v1', meRouter);
app.use('/api/v1', matchupsRouter);
app.use('/api/v1', lineupsRouter);
if (process.env.DEV_ENDPOINTS_ENABLED === 'true') {
  app.use('/api/v1', devRouter);
}

app.listen(port, () => {
  console.log(`API server listening on port ${port}`);
  startSimDispatcher();
});
