package com.sensorpulse.config;

import com.zaxxer.hikari.HikariDataSource;
import com.zaxxer.hikari.HikariPoolMXBean;
import javax.sql.DataSource;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

/** Blocks startup until Hikari has opened every connection (min == max). */
@Component
public class PoolWarmup implements ApplicationRunner {

    private final DataSource dataSource;

    public PoolWarmup(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    @Override
    public void run(ApplicationArguments args) throws Exception {
        if (!(dataSource instanceof HikariDataSource hikari)) {
            return;
        }
        // Hikari starts its pool lazily; the first getConnection() initializes it (and the MXBean).
        hikari.getConnection().close();
        HikariPoolMXBean pool = hikari.getHikariPoolMXBean();
        long deadline = System.nanoTime() + 30_000_000_000L;
        while (pool.getTotalConnections() < hikari.getMaximumPoolSize()) {
            if (System.nanoTime() > deadline) {
                throw new IllegalStateException("pool did not reach "
                        + hikari.getMaximumPoolSize() + " connections");
            }
            Thread.sleep(50);
        }
    }
}
