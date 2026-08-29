// AudioWorkletProcessor: convierte el audio del mic (Float32, en el sample rate del
// AudioContext — 16000Hz, pedido explícitamente al crearlo) a PCM16 y lo manda al hilo
// principal en bloques, para minimizar mensajes postMessage por segundo.
//
// No hace resampling acá: se asume que el AudioContext que lo instancia ya se creó con
// { sampleRate: 16000 } y que el navegador (Chromium/WebView2) resamplea el audio real del
// hardware para que llegue a este processor ya en 16kHz.

const SAMPLES_PER_MESSAGE = 1600; // 100ms a 16kHz — balance entre latencia y overhead de mensajes

class PcmCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = new Int16Array(SAMPLES_PER_MESSAGE);
    this.offset = 0;
  }

  process(inputs) {
    const input = inputs[0];
    const channel = input && input[0];
    if (!channel) return true;

    for (let i = 0; i < channel.length; i++) {
      const clamped = Math.max(-1, Math.min(1, channel[i]));
      this.buffer[this.offset] = clamped < 0 ? clamped * 32768 : clamped * 32767;
      this.offset++;

      if (this.offset === SAMPLES_PER_MESSAGE) {
        this.port.postMessage(this.buffer.buffer, [this.buffer.buffer]);
        this.buffer = new Int16Array(SAMPLES_PER_MESSAGE);
        this.offset = 0;
      }
    }

    return true;
  }
}

registerProcessor("pcm-capture-processor", PcmCaptureProcessor);
