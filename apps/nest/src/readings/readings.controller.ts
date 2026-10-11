import { Body, Controller, Get, Header, Param, Post, Query } from '@nestjs/common';
import type { Query as Q } from '../validation';
import { AuthGuard } from '../auth';
import { ReadingsService } from './readings.service';

const JSON_TYPE = 'application/json';

@AuthGuard
@Controller('readings')
export class ReadingsController {
  constructor(private readonly readings: ReadingsService) {}

  @Get('stats') // before :id
  @Header('Content-Type', JSON_TYPE)
  stats(@Query() q: Q) {
    return this.readings.stats(q);
  }

  @Get(':id')
  @Header('Content-Type', JSON_TYPE)
  getById(@Param('id') id: string) {
    return this.readings.getById(id);
  }

  @Get()
  @Header('Content-Type', JSON_TYPE)
  list(@Query() q: Q) {
    return this.readings.list(q);
  }

  @Post() // 201
  @Header('Content-Type', JSON_TYPE)
  create(@Body() body: unknown) {
    return this.readings.create(body);
  }

  @Post('batch') // 201
  @Header('Content-Type', JSON_TYPE)
  createBatch(@Body() body: unknown) {
    return this.readings.createBatch(body);
  }
}
