import 'dotenv/config';
import express from 'express';
import cors from 'cors';
import { meRouter } from './routes/me';

const app = express();
const port = process.env.PORT ?? 3000;

app.use(cors({ origin: process.env.CORS_ORIGIN ?? '*' }));
app.use(express.json());

app.use('/api/v1', meRouter);

app.listen(port, () => {
  console.log(`API server listening on port ${port}`);
});
