import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { HmacGuard } from './hmac.guard';
import { SessionStore } from './session-store.service';
import { SwapsController } from './swaps.controller';
import { SwapsService } from './swaps.service';

@Module({
  imports: [ConfigModule],
  controllers: [SwapsController],
  providers: [SwapsService, SessionStore, HmacGuard],
  exports: [SwapsService, SessionStore],
})
export class SwapsModule {}
