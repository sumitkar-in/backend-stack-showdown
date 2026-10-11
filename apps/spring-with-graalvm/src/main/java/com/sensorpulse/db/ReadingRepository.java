package com.sensorpulse.db;

import com.sensorpulse.model.DeviceRange;
import com.sensorpulse.model.NewReading;
import com.sensorpulse.model.Reading;
import com.sensorpulse.model.ReadingStats;
import com.sensorpulse.support.Timestamps;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

/** Raw parameterized SQL via JdbcTemplate; no ORM. */
@Repository
public class ReadingRepository {

    private static final RowMapper<Reading> READING = ReadingRepository::mapReading;

    private final JdbcTemplate jdbc;

    public ReadingRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    private static Reading mapReading(ResultSet rs, int row) throws SQLException {
        return new Reading(
                rs.getLong(1),
                rs.getInt(2),
                rs.getShort(3),
                rs.getShort(4),
                Timestamps.format(rs.getObject(5, OffsetDateTime.class)));
    }

    /** Empty list when the id does not exist. */
    public List<Reading> findById(long id) {
        return jdbc.query(Sql.BY_ID, READING, id);
    }

    public List<Reading> list(DeviceRange r, int limit, int offset) {
        return jdbc.query(Sql.LIST, READING, r.device(), r.from(), r.to(), limit, offset);
    }

    public ReadingStats stats(DeviceRange r) {
        return jdbc.queryForObject(
                Sql.STATS,
                (rs, row) -> new ReadingStats(
                        r.device(),
                        rs.getLong(1),
                        rs.getLong(2),
                        rs.getLong(3),
                        rs.getObject(4, Short.class),
                        rs.getObject(5, Short.class)),
                r.device(), r.from(), r.to());
    }

    public Reading insert(NewReading n) {
        return jdbc.queryForObject(
                Sql.INSERT, READING, n.deviceId(), n.temperatureCenti(), n.humidityBp(), n.observedAt());
    }

    /** One multi-row INSERT: atomic, all-or-nothing. */
    public int insertBatch(List<NewReading> items) {
        Object[] args = new Object[items.size() * 4];
        int i = 0;
        for (NewReading n : items) {
            args[i++] = n.deviceId();
            args[i++] = n.temperatureCenti();
            args[i++] = n.humidityBp();
            args[i++] = n.observedAt();
        }
        jdbc.update(Sql.batchInsert(items.size()), args);
        return items.size();
    }
}
