package com.regtrack.backend.controller;

import com.regtrack.backend.dto.WebhookDtos.ChangeEventResponse;
import com.regtrack.backend.service.WebhookService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/events")
@RequiredArgsConstructor
public class EventController {

    private final WebhookService webhookService;

    @GetMapping
    public ResponseEntity<List<ChangeEventResponse>> list() {
        return ResponseEntity.ok(webhookService.list());
    }
}
