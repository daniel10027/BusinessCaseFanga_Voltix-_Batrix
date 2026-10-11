import { Body, Controller, HttpCode, HttpStatus, Post, UseGuards } from '@nestjs/common';
import { BatterySwappedPayload } from './dto/battery-swapped-payload.dto';
import { FangaWebhookEvent } from './dto/webhook-event.dto';
import { HmacGuard } from './hmac.guard';
import { SwapsService } from './swaps.service';

/**
 * `POST /webhooks/fanga` : recoit les evenements du relais outbox de
 * fanga-ingest (brief, 5.7). Seul `battery.swapped` est actionne par ce
 * module bonus — les autres types (faulted, unknown_detected,
 * offline/online) seraient routes vers d'autres modules dans une vraie
 * implementation, mais sont acceptes (204) pour ne jamais faire echouer le
 * relais sur un type qu'on ne gere pas encore.
 */
@Controller('webhooks/fanga')
export class SwapsController {
  constructor(private readonly swaps: SwapsService) {}

  @Post()
  @UseGuards(HmacGuard)
  @HttpCode(HttpStatus.NO_CONTENT)
  handleWebhook(@Body() event: FangaWebhookEvent<unknown>): void {
    if (event.type === 'battery.swapped') {
      this.swaps.handleBatterySwapped(event.event_id, event.payload as BatterySwappedPayload);
    }
  }
}
