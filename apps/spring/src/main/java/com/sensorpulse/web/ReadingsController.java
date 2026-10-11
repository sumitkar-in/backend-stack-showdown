package com.sensorpulse.web;

import com.fasterxml.jackson.databind.JsonNode;
import com.sensorpulse.db.ReadingRepository;
import com.sensorpulse.model.DeviceRange;
import com.sensorpulse.model.Inserted;
import com.sensorpulse.model.Reading;
import com.sensorpulse.model.ReadingPage;
import com.sensorpulse.model.NewReading;
import jakarta.servlet.http.HttpServletRequest;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReadingsController {

    private final ReadingRepository repo;

    public ReadingsController(ReadingRepository repo) {
        this.repo = repo;
    }

    // Literal path wins over /readings/{id} in Spring's matching.
    @GetMapping("/readings/stats")
    public ResponseEntity<byte[]> stats(HttpServletRequest req) {
        DeviceRange range = Validation.deviceRange(req);
        return Json.respond(HttpStatus.OK, repo.stats(range));
    }

    @GetMapping("/readings/{id}")
    public ResponseEntity<byte[]> byId(@PathVariable String id) {
        List<Reading> found = repo.findById(Validation.id(id));
        if (found.isEmpty()) {
            throw ApiException.notFound();
        }
        return Json.respond(HttpStatus.OK, found.get(0));
    }

    @GetMapping("/readings")
    public ResponseEntity<byte[]> list(HttpServletRequest req) {
        DeviceRange range = Validation.deviceRange(req);
        Validation.Paging page = Validation.paging(req);
        List<Reading> items = repo.list(range, page.limit(), page.offset());
        return Json.respond(HttpStatus.OK, new ReadingPage(items, page.limit(), page.offset()));
    }

    @PostMapping("/readings")
    public ResponseEntity<byte[]> create(@RequestBody byte[] body) {
        NewReading reading = Validation.reading(Json.parse(body));
        return Json.respond(HttpStatus.CREATED, repo.insert(reading));
    }

    @PostMapping("/readings/batch")
    public ResponseEntity<byte[]> createBatch(@RequestBody byte[] body) {
        JsonNode root = Json.parse(body);
        if (!root.isObject()) {
            throw ApiException.badRequest();
        }
        int inserted = repo.insertBatch(Validation.batch(root));
        return Json.respond(HttpStatus.CREATED, new Inserted(inserted));
    }
}
