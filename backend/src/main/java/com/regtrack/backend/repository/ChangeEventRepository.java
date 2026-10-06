package com.regtrack.backend.repository;

import com.regtrack.backend.model.ChangeEvent;
import com.regtrack.backend.model.ChangeStatus;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface ChangeEventRepository extends JpaRepository<ChangeEvent, Long> {

    List<ChangeEvent> findTop50ByOrderByReceivedAtDesc();

    List<ChangeEvent> findByStatusOrderByReceivedAtDesc(ChangeStatus status);

    long countByStatus(ChangeStatus status);
}
