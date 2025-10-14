document.addEventListener('DOMContentLoaded', () => {
    const video = document.getElementById('video');
    const streamUrl = document.body.dataset.streamUrl;

    if (!streamUrl) {
        console.error('Stream URL is not set. Please add data-stream-url attribute to the body tag.');
        return;
    }

    if (Hls.isSupported()) {
        const hls = new Hls();
        hls.loadSource(streamUrl);
        hls.attachMedia(video);
        hls.on(Hls.Events.MANIFEST_PARSED, function() {
            video.play().catch(error => console.error('Autoplay was prevented:', error));
        });
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
        video.src = streamUrl;
        video.addEventListener('loadedmetadata', function() {
            video.play().catch(error => console.error('Autoplay was prevented:', error));
        });
    }
});
