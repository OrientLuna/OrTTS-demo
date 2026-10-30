#include "ortts_engine.h"
#include <stdio.h>
#include <stdlib.h>

static int on_pcm(void *user, const float *pcm, size_t count, int32_t rate) {
    size_t *received = (size_t *)user;
    (void)pcm;
    if (rate != 24000) return 1;
    *received += count; /* A host app would copy/enqueue this chunk. */
    return 0;
}

int main(int argc, char **argv) {
    if (argc != 5) {
        fprintf(stderr, "usage: stream ASSET_ROOT P3|P5 BRIDGE_SHA TEXT\n");
        return 2;
    }
    ortts_config config = {sizeof(config), argv[1], argv[2], NULL, argv[3], 4, 1};
    ortts_request request = {sizeof(request), argv[4], 20261023, 128};
    ortts_engine *engine = NULL;
    ortts_audio *audio = NULL;
    size_t received = 0;
    int status = ortts_engine_create(&config, &engine);
    if (!status)
        status = ortts_engine_synthesize(engine, &request, on_pcm, &received, &audio);
    if (status) {
        fprintf(stderr, "%s\n", ortts_last_error());
    } else {
        ortts_metrics metrics;
        ortts_audio_metrics(audio, &metrics);
        printf("samples=%zu callback_samples=%zu chunks=%zu API_ms=%.3f\n",
               ortts_audio_sample_count(audio), received, metrics.chunks, metrics.api_ms);
    }
    ortts_audio_free(audio);
    ortts_engine_free(engine);
    return status ? 1 : 0;
}
