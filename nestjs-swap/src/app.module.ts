import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { SwapsModule } from './swaps/swaps.module';

@Module({
  imports: [ConfigModule.forRoot({ isGlobal: true }), SwapsModule],
})
export class AppModule {}
