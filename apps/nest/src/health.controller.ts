import { Controller, Get, Header } from '@nestjs/common';
import { BODY } from './errors';

@Controller('health')
export class HealthController {
  @Get()
  @Header('Content-Type', 'application/json')
  health(): string {
    return BODY.health; // no DB access
  }
}
