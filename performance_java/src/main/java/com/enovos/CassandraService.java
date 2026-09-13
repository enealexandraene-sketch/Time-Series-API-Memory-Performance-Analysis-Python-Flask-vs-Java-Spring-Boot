package com.enovos;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import org.springframework.stereotype.Service;
import javax.annotation.PreDestroy;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.stream.Collectors;

@Service
public class CassandraService {

    private final CqlSession cqlSession;
    private final ExecutorService executorService;
    
    public CassandraService(CqlSession cqlSession) {
        this.cqlSession = cqlSession;
        // Create a thread pool for parallel processing
        // Using 10 threads as a reasonable default for database operations
        this.executorService = Executors.newFixedThreadPool(10);
    }
    
    @PreDestroy
    public void cleanup() {
        if (executorService != null && !executorService.isShutdown()) {
            executorService.shutdown();
        }
    }

    public String getCassandraVersion() {
        try {
            // Select the release_version from the system.local table:
            ResultSet rs = cqlSession.execute("select release_version from system.local");
            Row row = rs.one();
            //Print the results of the CQL query to the console:
            if (row != null) {
                return row.getString("release_version");
            } else {
                return "An error occurred.";
            }
        } catch (Exception e) {
            return "Error connecting to Cassandra: " + e.getMessage();
        }
    }
    
    public HelloController.Day2DayResponse getDay2DayInfo(HelloController.Day2DayRequest request) {
        try {
            // Parse the books list
            List<String> pfmList = new ArrayList<>();
            if (request.getBooks() != null && !request.getBooks().trim().isEmpty()) {
                String[] books = request.getBooks().split(",");
                for (String book : books) {
                    pfmList.add(book.trim());
                }
            }
            
            // Validate required fields
            if (request.getAs_of_op_old() == null || "null".equals(request.getAs_of_op_old()) ||
                request.getAs_of_op_new() == null || "null".equals(request.getAs_of_op_new())) {
                return new HelloController.Day2DayResponse(
                    "No data previous for as_of_op_old = " + request.getAs_of_op_old() + 
                    " or as_of_op_new = " + request.getAs_of_op_new(), 
                    false, 
                    new ArrayList<>()
                );
            }
            
            // Parse dates - handle URL-encoded datetime format
            DateTimeFormatter formatter = DateTimeFormatter.ofPattern("yyyy-MM-dd");
            LocalDate asOfOpOld = LocalDate.parse(request.getAs_of_op_old());
            LocalDate asOfOpNew = LocalDate.parse(request.getAs_of_op_new());
            
            // Parse datetime strings, handling URL encoding
            String tsStartStr = request.getTs_start().replace("%3A", ":").replace("%2B", "+");
            String tsEndStr = request.getTs_end().replace("%3A", ":").replace("%2B", "+");
            
            // Parse with timezone handling
            LocalDateTime tsStart = LocalDateTime.parse(tsStartStr.substring(0, 19)); // Remove timezone info
            LocalDateTime tsEnd = LocalDateTime.parse(tsEndStr.substring(0, 19)); // Remove timezone info
            
            // Process books in parallel
            List<CompletableFuture<BookProcessingResult>> futures = pfmList.stream()
                .map(bookName -> CompletableFuture.supplyAsync(() -> {
                    System.out.println("Processing book: " + bookName);
                    
                    try {
                        // Get old power data
                        List<PowerData> opDfOld = getOpPowerData(
                            asOfOpOld, 
                            bookName, 
                            tsStart, 
                            tsEnd
                        );
                        
                        System.out.println("Old data count for " + bookName + ": " + opDfOld.size());
                        
                        // Get new power data
                        List<PowerData> opDfNew = getOpPowerData(
                            asOfOpNew, 
                            bookName, 
                            tsStart, 
                            tsEnd
                        );
                        
                        System.out.println("New data count for " + bookName + ": " + opDfNew.size());
                        
                        // Check if data exists
                        if (opDfOld.isEmpty()) {
                            return new BookProcessingResult(bookName, false, "There are no data for the old as_of");
                        }
                        
                        if (opDfNew.isEmpty()) {
                            return new BookProcessingResult(bookName, false, "There are no data for the new as_of");
                        }
                        
                        return new BookProcessingResult(bookName, true, null);
                        
                    } catch (Exception e) {
                        System.err.println("Error processing book " + bookName + ": " + e.getMessage());
                        return new BookProcessingResult(bookName, false, "Error processing book: " + e.getMessage());
                    }
                }, executorService))
                .collect(Collectors.toList());
            
            // Wait for all futures to complete and collect results
            List<BookProcessingResult> results = futures.stream()
                .map(CompletableFuture::join)
                .collect(Collectors.toList());
            
            // Check for any failures
            for (BookProcessingResult result : results) {
                if (!result.isSuccess()) {
                    return new HelloController.Day2DayResponse(
                        result.getErrorMessage(), 
                        false, 
                        results.stream()
                            .filter(BookProcessingResult::isSuccess)
                            .map(BookProcessingResult::getBookName)
                            .collect(Collectors.toList())
                    );
                }
            }
            
            // All books processed successfully
            List<String> processedBooks = results.stream()
                .map(BookProcessingResult::getBookName)
                .collect(Collectors.toList());
            
            return new HelloController.Day2DayResponse(
                "Day2Day information processed successfully for " + processedBooks.size() + " books", 
                true, 
                processedBooks
            );
            
        } catch (Exception e) {
            return new HelloController.Day2DayResponse(
                "Error processing day2day information: " + e.getMessage(), 
                false, 
                new ArrayList<>()
            );
        }
    }
    
    private List<PowerData> getOpPowerData(LocalDate asOf, String bookOp, LocalDateTime tsStart, LocalDateTime tsEnd) {
        List<PowerData> powerDataList = new ArrayList<>();
        
        try {
            // Convert LocalDateTime to Instant for Cassandra timestamp fields
            Instant tsStartInstant = tsStart.atZone(java.time.ZoneOffset.UTC).toInstant();
            Instant tsEndInstant = tsEnd.atZone(java.time.ZoneOffset.UTC).toInstant();
            
            // Query based on the Python implementation
            // Using the exact table name and column names from the Python query
            String query = "SELECT time, value, is_peak FROM series_op_power WHERE as_of = ? AND name = ? AND time >= ? AND time < ?";
            
            System.out.println("Executing query: " + query);
            System.out.println("Parameters: asOf=" + asOf + ", bookOp=" + bookOp + ", tsStart=" + tsStartInstant + ", tsEnd=" + tsEndInstant);
            
            ResultSet rs = cqlSession.execute(query, asOf, bookOp, tsStartInstant, tsEndInstant);
            
            for (Row row : rs) {
                PowerData powerData = new PowerData();
                // Map the row data to PowerData object based on the actual schema
                // Handle time as Instant (timestamp) and convert to string for display
                Instant timeInstant = row.getInstant("time");
                powerData.setTime(timeInstant != null ? timeInstant.toString() : null);
                powerData.setValue(row.getDouble("value"));
                powerData.setIsPeak(row.getBoolean("is_peak"));
                powerDataList.add(powerData);
            }
            
        } catch (Exception e) {
            // Log the error but don't fail the entire operation
            System.err.println("Error querying power data: " + e.getMessage());
        }
        
        return powerDataList;
    }
    
    // PowerData class based on the actual Cassandra schema
    private static class PowerData {
        private String time;
        private Double value;
        private Boolean isPeak;
        
        // Getters and setters
        public String getTime() { return time; }
        public void setTime(String time) { this.time = time; }
        public Double getValue() { return value; }
        public void setValue(Double value) { this.value = value; }
        public Boolean getIsPeak() { return isPeak; }
        public void setIsPeak(Boolean isPeak) { this.isPeak = isPeak; }
    }
    
    // Result class for parallel book processing
    private static class BookProcessingResult {
        private final String bookName;
        private final boolean success;
        private final String errorMessage;
        
        public BookProcessingResult(String bookName, boolean success, String errorMessage) {
            this.bookName = bookName;
            this.success = success;
            this.errorMessage = errorMessage;
        }
        
        public String getBookName() { return bookName; }
        public boolean isSuccess() { return success; }
        public String getErrorMessage() { return errorMessage; }
    }
}
