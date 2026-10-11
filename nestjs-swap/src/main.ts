import 'reflect-metadata';
import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';

async function bootstrap(): Promise<void> {
  // `rawBody: true` : necessaire a HmacGuard pour verifier la signature sur
  // les octets exacts envoyes par fanga-ingest, pas sur une re-serialisation.
  const app = await NestFactory.create(AppModule, { rawBody: true });
  await app.listen(process.env.PORT ?? 3000);
}

bootstrap();
