package com.enovos;

import org.springframework.web.bind.annotation.*;
import java.util.List;

@RestController
public class HelloController {
    private final CassandraService cassandraService;
    
    public HelloController(CassandraService cassandraService) {
        this.cassandraService = cassandraService;
    }

    @RequestMapping("/")
    String hello() {
        return "Hello World!";
    }
    
    // Cassandra sample
    @RequestMapping("cassandra")
    String cassandra() {
        return cassandraService.getCassandraVersion();
    }
    
    // Day2Day information endpoint
    @GetMapping("d2d_new_2/power")
    public Day2DayResponse getDay2DayInfo(
            @RequestParam("books") String books,
            @RequestParam("as_of_op_old") String asOfOpOld,
            @RequestParam("as_of_op_new") String asOfOpNew,
            @RequestParam("ts_start") String tsStart,
            @RequestParam("ts_end") String tsEnd,
            @RequestParam(value = "aggr", defaultValue = "hour") String aggr,
            @RequestParam(value = "user", required = false) String user) {
        
        Day2DayRequest request = new Day2DayRequest();
        request.setBooks(books);
        request.setAs_of_op_old(asOfOpOld);
        request.setAs_of_op_new(asOfOpNew);
        request.setTs_start(tsStart);
        request.setTs_end(tsEnd);
        
        return cassandraService.getDay2DayInfo(request);
    }
    
    // Data models
    public static class Day2DayRequest {
        private String books;
        private String as_of_op_old;
        private String as_of_op_new;
        private String ts_start;
        private String ts_end;
        
        // Getters and setters
        public String getBooks() { return books; }
        public void setBooks(String books) { this.books = books; }
        public String getAs_of_op_old() { return as_of_op_old; }
        public void setAs_of_op_old(String as_of_op_old) { this.as_of_op_old = as_of_op_old; }
        public String getAs_of_op_new() { return as_of_op_new; }
        public void setAs_of_op_new(String as_of_op_new) { this.as_of_op_new = as_of_op_new; }
        public String getTs_start() { return ts_start; }
        public void setTs_start(String ts_start) { this.ts_start = ts_start; }
        public String getTs_end() { return ts_end; }
        public void setTs_end(String ts_end) { this.ts_end = ts_end; }
    }
    
    public static class Day2DayResponse {
        private String message;
        private boolean success;
        private List<String> processedBooks;
        
        public Day2DayResponse(String message, boolean success, List<String> processedBooks) {
            this.message = message;
            this.success = success;
            this.processedBooks = processedBooks;
        }
        
        // Getters and setters
        public String getMessage() { return message; }
        public void setMessage(String message) { this.message = message; }
        public boolean isSuccess() { return success; }
        public void setSuccess(boolean success) { this.success = success; }
        public List<String> getProcessedBooks() { return processedBooks; }
        public void setProcessedBooks(List<String> processedBooks) { this.processedBooks = processedBooks; }
    }
}
