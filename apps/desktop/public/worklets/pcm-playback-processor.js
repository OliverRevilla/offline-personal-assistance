// AudioWorkletProcessor: reproduce en orden los chunks de audio (Float32, ya normalizado)
// que le llegan por postMessage desde el hilo principal. Si se queda sin datos, escribe
// silencio en vez de trabarse (subrun normal si la síntesis va más lenta que la reproducción).

class PcmPlaybackProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.queue = [];
    this.readOffset = 0;

    this.port.onmessage = (event) => {
      this.queue.push(new Float32Array(event.data));
    };
  }

  process(_inputs, outputs) {
    const output = outputs[0][0];
    if (!output) return true;

    let written = 0;
    while (written < output.length) {
      if (this.queue.length === 0) {
        output.fill(0, written);
        return true;
      }

      const chunk = this.queue[0];
      const disponible = chunk.length - this.readOffset;
      const necesario = output.length - written;
      const tomar = Math.min(disponible, necesario);

      output.set(chunk.subarray(this.readOffset, this.readOffset + tomar), written);
      written += tomar;
      this.readOffset += tomar;

      if (this.readOffset >= chunk.length) {
        this.queue.shift();
        this.readOffset = 0;
      }
    }

    return true;
  }
}

registerProcessor("pcm-playback-processor", PcmPlaybackProcessor);
