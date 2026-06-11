"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { createTrainingWs, getTrainingStatus } from "@/lib/api";
import type { WsMessage, ActiveTrainingRun } from "@/lib/types";

// ─── Types ─────────────────────────────────────────────────────

export interface TrainingWebSocketState {
  /** Connection status */
  connected: boolean;
  /** Training progress (0–1) */
  progress: number;
  /** Current training loss (if reported) */
  loss: number | null;
  /** Current training step (if reported) */
  step: number | null;
  /** Training status from WebSocket */
  status: "idle" | "queued" | "running" | "completed" | "failed";
  /** Time since last status update in ms */
  lastUpdate: number;
}

export interface UseTrainingWebSocketOptions {
  /** Whether to activate the WebSocket connection */
  enabled?: boolean;
  /** Initial run data from HTTP (used to seed progress/status before WS connects) */
  run?: ActiveTrainingRun | null;
  /** Called when training completes (WebSocket closes and poll confirms) */
  onComplete?: () => void;
  /** Called when connection state changes */
  onConnectionChange?: (connected: boolean) => void;
  /** Poll interval in ms for checking training completion after WS close (default: 2000) */
  pollInterval?: number;
}

/**
 * Reusable hook that connects to the training progress WebSocket.
 *
 * - Connects when `enabled` is true
 * - Seeds initial progress/status from `run` object
 * - Handles `training_progress` and `training_started` messages
 * - Polls HTTP after WS closes to detect completion
 * - Cleans up on unmount or disable
 */
export function useTrainingWebSocket(
  options: UseTrainingWebSocketOptions = {}
): TrainingWebSocketState {
  const { enabled = true, run, onComplete, onConnectionChange, pollInterval = 2000 } = options;

  const [state, setState] = useState<TrainingWebSocketState>(() => ({
    connected: false,
    progress: run?.progress ?? 0,
    loss: null,
    step: null,
    status: run?.status ?? "idle",
    lastUpdate: Date.now(),
  }));

  const wsRef = useRef<WebSocket | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval>>();
  const onCompleteRef = useRef(onComplete);
  const onConnectionChangeRef = useRef(onConnectionChange);

  onCompleteRef.current = onComplete;
  onConnectionChangeRef.current = onConnectionChange;

  const updateState = useCallback((partial: Partial<TrainingWebSocketState>) => {
    setState((prev) => ({ ...prev, ...partial, lastUpdate: Date.now() }));
  }, []);

  useEffect(() => {
    if (!enabled) return;

    const ws = createTrainingWs();
    wsRef.current = ws;

    ws.onopen = () => {
      updateState({ connected: true });
      onConnectionChangeRef.current?.(true);
    };

    ws.onmessage = (event) => {
      try {
        const msg: WsMessage = JSON.parse(event.data);

        if (msg.type === "training_progress") {
          // Only include loss/step when they're actually in the message
          const update: Partial<TrainingWebSocketState> = {
            progress: msg.progress,
            status: "running",
          };
          if (msg.loss !== undefined) update.loss = msg.loss;
          if (msg.step !== undefined) update.step = msg.step;
          updateState(update);
        }

        if (msg.type === "training_started") {
          updateState({ status: "running" });
        }
      } catch {
        // Ignore malformed messages
      }
    };

    ws.onclose = () => {
      updateState({ connected: false });
      onConnectionChangeRef.current?.(false);

      pollRef.current = setInterval(async () => {
        try {
          const statusData = await getTrainingStatus();
          if (!statusData.active_run) {
            clearInterval(pollRef.current);
            pollRef.current = undefined;
            onCompleteRef.current?.();
          }
        } catch {
          clearInterval(pollRef.current);
          pollRef.current = undefined;
        }
      }, pollInterval);
    };

    ws.onerror = () => {
      updateState({ connected: false });
      onConnectionChangeRef.current?.(false);
    };

    return () => {
      ws.close();
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = undefined;
      }
    };
  }, [enabled, pollInterval, updateState]);

  return state;
}
