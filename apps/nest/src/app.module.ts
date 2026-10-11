import { Module } from '@nestjs/common';
import { DbModule } from './db';
import { HealthController } from './health.controller';
import { ReadingsController } from './readings/readings.controller';
import { ReadingsService } from './readings/readings.service';

@Module({
  imports: [DbModule],
  controllers: [HealthController, ReadingsController],
  providers: [ReadingsService],
})
export class AppModule {}
