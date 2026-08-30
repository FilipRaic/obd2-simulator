// can_task.h
// High-priority FreeRTOS task: owns the DTC bank, the
// sensor table and the simulation profile. It receives CAN frames from the
// MCP2515 and answers them through the protocol core, applies Commands from
// the UI task and republishes a Snapshot every tick.
#pragma once

// Create the queues, initialise the CAN controller, load the start-up
// scenario (last used, else factory) and start the task. Call once from
// setup(), after hal::spi_bus_init() and storage::init().
void can_task_start();
