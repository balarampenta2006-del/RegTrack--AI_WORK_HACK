package com.regtrack.backend.controller;

import com.regtrack.backend.dto.WebhookDtos.WebhookAckResponse;
import com.regtrack.backend.service.WebhookService;
import jakarta.servlet.http.HttpServletRequest;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/webhooks")
@RequiredArgsConstructor
public class WebhookController {

    private final WebhookService webhookService;

    /**
     * ChangeDetection.io / n8n change notification.
     * Authenticate with header X-Webhook-Signature: sha256=&lt;hex hmac of raw body&gt;
     * or X-Webhook-Token: &lt;shared secret&gt;.
     */
    @PostMapping("/changedetection")
    public ResponseEntity<WebhookAckResponse> receive(@RequestBody String body,
                                                      HttpServletRequest request) {
        WebhookAckResponse ack = webhookService.receive(body, request.getRemoteAddr());
        return ResponseEntity.status(HttpStatus.ACCEPTED).body(ack);
    }
}
