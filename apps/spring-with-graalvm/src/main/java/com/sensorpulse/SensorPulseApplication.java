package com.sensorpulse;

import com.sensorpulse.model.Inserted;
import com.sensorpulse.model.NewReading;
import com.sensorpulse.model.Reading;
import com.sensorpulse.model.ReadingPage;
import com.sensorpulse.model.ReadingStats;
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

// Json.respond() serializes these records with a plain ObjectMapper, which Spring AOT cannot see on its own.
@RegisterReflectionForBinding({Reading.class, ReadingPage.class, ReadingStats.class, Inserted.class, NewReading.class})
@SpringBootApplication
public class SensorPulseApplication {
    public static void main(String[] args) {
        SpringApplication.run(SensorPulseApplication.class, args);
    }
}
