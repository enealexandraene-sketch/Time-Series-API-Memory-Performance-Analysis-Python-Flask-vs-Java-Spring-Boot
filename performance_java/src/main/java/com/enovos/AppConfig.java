package com.enovos;

import com.datastax.oss.driver.api.core.CqlSession;
import net.sf.log4jdbc.sql.jdbcapi.DataSourceSpy;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.jdbc.DataSourceBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

import javax.sql.DataSource;

import java.net.InetSocketAddress;
import java.nio.file.Paths;

@Configuration
public class AppConfig {

    @Bean
    @ConfigurationProperties(prefix = "spring.datasource")
    DataSource realDataSource() {
        return DataSourceBuilder.create().build();
    }

    @Bean
    @Primary
    DataSource dataSource() {
        return new DataSourceSpy(realDataSource());
    }
    
    @Bean
    CqlSession cqlSession() {
        return CqlSession.builder()
    .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
    .withLocalDatacenter("datacenter1")
    .withAuthCredentials("cassandra", "cassandra")
    .withKeyspace("local")
    .build();
    }
}