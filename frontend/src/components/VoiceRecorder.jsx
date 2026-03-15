import { useCallback, useRef, useState } from "react";
import { Circle, Mic, Square } from "lucide-react";

import { Button } from "@/components/ui/button";

/**
 * In-browser voice recorder using MediaRecorder API.
 * Outputs a base64 data URL (audio/webm) via onRecordingComplete callback.
 */
export const VoiceRecorder = ({ onRecordingComplete, disabled = false }) => {
  const [isRecording, setIsRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [audioPreview, setAudioPreview] = useState(null);
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const timerRef = useRef(null);

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm;codecs=opus" });
      mediaRecorderRef.current = mediaRecorder;
      chunksRef.current = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      mediaRecorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        const url = URL.createObjectURL(blob);
        setAudioPreview(url);

        // Convert to base64 data URL
        const reader = new FileReader();
        reader.onloadend = () => {
          onRecordingComplete?.(reader.result);
        };
        reader.readAsDataURL(blob);
      };

      mediaRecorder.start(250);
      setIsRecording(true);
      setElapsed(0);
      setAudioPreview(null);
      timerRef.current = setInterval(() => setElapsed((s) => s + 1), 1000);
    } catch {
      /* permission denied or no mic */
    }
  }, [onRecordingComplete]);

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current?.state === "recording") {
      mediaRecorderRef.current.stop();
    }
    setIsRecording(false);
    clearInterval(timerRef.current);
  }, []);

  const clearRecording = useCallback(() => {
    setAudioPreview(null);
    setElapsed(0);
    onRecordingComplete?.(null);
  }, [onRecordingComplete]);

  const formatTime = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;

  return (
    <div className="space-y-2" data-testid="voice-recorder">
      <div className="flex items-center gap-3">
        {isRecording ? (
          <Button
            className="rounded-full gap-2"
            data-testid="voice-recorder-stop"
            onClick={stopRecording}
            size="sm"
            variant="destructive"
          >
            <Square className="h-3 w-3 fill-current" />
            Stop · {formatTime(elapsed)}
          </Button>
        ) : (
          <Button
            className="rounded-full gap-2"
            data-testid="voice-recorder-start"
            disabled={disabled}
            onClick={startRecording}
            size="sm"
            variant="outline"
          >
            <Mic className="h-3.5 w-3.5" />
            Record voice note
          </Button>
        )}
        {isRecording && (
          <span className="flex items-center gap-1.5 text-xs font-medium text-destructive">
            <Circle className="h-2 w-2 fill-destructive animate-pulse" />
            Recording...
          </span>
        )}
      </div>
      {audioPreview && !isRecording && (
        <div className="flex items-center gap-3 rounded-xl border border-border/60 bg-muted/30 p-3">
          <audio className="flex-1 h-8" controls data-testid="voice-recorder-preview" src={audioPreview} />
          <button
            className="text-xs font-medium text-destructive hover:underline"
            data-testid="voice-recorder-clear"
            onClick={clearRecording}
          >
            Discard
          </button>
        </div>
      )}
    </div>
  );
};
