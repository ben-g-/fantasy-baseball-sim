import 'dotenv/config';
import express from 'express';
import cors from 'cors';
import { meRouter } from './routes/me';
import { devRouter } from './routes/dev';

const app = express();
const port = process.env.PORT ?? 3000;

app.use(cors({ origin: process.env.CORS_ORIGIN ?? '*' }));
app.use(express.json());

app.use('/api/v1', meRouter);
if (process.env.DEV_ENDPOINTS_ENABLED === 'true') {
  app.use('/api/v1', devRouter);
}

app.listen(port, () => {
  console.log(`API server listening on port ${port}`);
});
