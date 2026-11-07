'use strict';

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

// ==================================================
// Configuration
// ==================================================

const FFMPEG = process.env.FFMPEG_PATH || 'ffmpeg';
const FFPROBE = process.env.FFPROBE_PATH || 'ffprobe';

const WORKDIR = fs.mkdtempSync(
    path.join(os.tmpdir(), 'ffmpeg-runtime-test-')
);

const SAMPLE_RATE = 44100;
const CHANNELS = 2;
const DURATION = 2;

const IMAGE_WIDTH = 320;
const IMAGE_HEIGHT = 240;

const TIMEOUT = 30000;

// ==================================================
// Results & Detailed Logging
// ==================================================

let passed = 0;
let failed = 0;
let skipped = 0;

const results = [];

function formatBytes(bytes) {
    if (bytes === undefined || bytes === null) return 'N/A';
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function pass(label, durationMs, details = {}) {
    passed++;
    results.push({ label, status: 'PASS', durationMs, details });
    const detailStr = Object.keys(details).length > 0 
        ? ` | ${Object.entries(details).map(([k, v]) => `${k}: ${v}`).join(', ')}`
        : '';
    console.log(`  [PASS] ${label} (${durationMs}ms)${detailStr}`);
}

function fail(label, durationMs, error) {
    failed++;
    results.push({ label, status: 'FAIL', durationMs, error: error.message });
    console.log(`  [FAIL] ${label} (${durationMs}ms): ${error.message}`);
}

function skip(label, reason) {
    skipped++;
    results.push({ label, status: 'SKIP', error: reason });
    console.log(`  [SKIP] ${label}: ${reason}`);
}

function check(label, callback) {
    const start = Date.now();
    try {
        const details = callback() || {};
        const durationMs = Date.now() - start;
        pass(label, durationMs, details);
        return true;
    } catch (error) {
        const durationMs = Date.now() - start;
        fail(label, durationMs, error);
        return false;
    }
}

// ==================================================
// Audio & Image Format Definitions
// ==================================================

const audioFormats = [
    { name: 'MP3', encoder: 'libmp3lame', decoder: 'mp3', codec: 'mp3', ext: 'mp3', muxer: 'mp3', demuxer: 'mp3', required: true },
    { name: 'AAC', encoder: 'aac', decoder: 'aac', codec: 'aac', ext: 'aac', muxer: 'adts', demuxer: 'aac', required: true },
    { name: 'M4A', encoder: 'aac', decoder: 'aac', codec: 'aac', ext: 'm4a', muxer: 'ipod', demuxer: 'mov', required: true },
    { name: 'M4B', encoder: 'aac', decoder: 'aac', codec: 'aac', ext: 'm4b', muxer: 'ipod', demuxer: 'mov', required: true },
    { name: 'FLAC', encoder: 'flac', decoder: 'flac', codec: 'flac', ext: 'flac', muxer: 'flac', demuxer: 'flac', required: true },
    { name: 'WAV', encoder: 'pcm_s16le', decoder: 'pcm_s16le', codec: 'pcm_s16le', ext: 'wav', muxer: 'wav', demuxer: 'wav', required: true },
    { name: 'OGG Vorbis', encoder: 'libvorbis', decoder: 'vorbis', codec: 'vorbis', ext: 'ogg', muxer: 'ogg', demuxer: 'ogg', required: true },
    { name: 'Opus', encoder: 'libopus', decoder: 'opus', codec: 'opus', ext: 'opus', muxer: 'ogg', demuxer: 'ogg', required: true },
    { name: 'WMA v2', encoder: 'wmav2', decoder: 'wmav2', codec: 'wmav2', ext: 'wma', muxer: 'asf', demuxer: 'asf', required: true },
    { name: 'AIFF', encoder: 'pcm_s16be', decoder: 'pcm_s16be', codec: 'pcm_s16be', ext: 'aiff', muxer: 'aiff', demuxer: 'aiff', required: true },
    { name: 'ALAC', encoder: 'alac', decoder: 'alac', codec: 'alac', ext: 'm4a', muxer: 'ipod', demuxer: 'mov', required: true },
    { name: 'AC3', encoder: 'ac3', decoder: 'ac3', codec: 'ac3', ext: 'ac3', muxer: 'ac3', demuxer: 'ac3', required: true },
    { name: 'E-AC3', encoder: 'eac3', decoder: 'eac3', codec: 'eac3', ext: 'eac3', muxer: 'eac3', demuxer: 'eac3', required: true }
];
const imageFormats = [
    { name: 'JPEG', encoder: 'mjpeg', decoder: 'mjpeg', codec: 'mjpeg', ext: 'jpg', muxer: 'image2', demuxer: 'image2', required: true },
    { name: 'PNG', encoder: 'png', decoder: 'png', codec: 'png', ext: 'png', muxer: 'image2', demuxer: 'image2', required: true },
    { name: 'WebP', encoder: 'libwebp', decoder: 'webp', codec: 'webp', ext: 'webp', muxer: 'image2', demuxer: 'image2', required: true },
    { name: 'GIF', encoder: 'gif', decoder: 'gif', codec: 'gif', ext: 'gif', muxer: 'gif', demuxer: 'gif', required: true },
    { name: 'BMP', encoder: 'bmp', decoder: 'bmp', codec: 'bmp', ext: 'bmp', muxer: 'image2', demuxer: 'image2', required: true },
    { name: 'TIFF', encoder: 'tiff', decoder: 'tiff', codec: 'tiff', ext: 'tiff', muxer: 'image2', demuxer: 'image2', required: true },
    { name: 'JPEG 2000', encoder: 'jpeg2000', decoder: 'jpeg2000', codec: 'jpeg2000', ext: 'jp2', muxer: 'image2', demuxer: 'image2', required: true },
    { name: 'AVIF', encoder: 'libsvtav1', decoder: 'av1', codec: 'av1', ext: 'avif', muxer: 'image2', demuxer: 'image2', required: true },
    { name: 'TGA (Truevision Targa)', encoder: 'targa', decoder: 'targa', codec: 'targa', ext: 'tga', muxer: 'image2', demuxer: 'image2', required: true },
    { name: 'PAM (Portable Arbitrary Map)', encoder: 'pam', decoder: 'pam', codec: 'pam', ext: 'pam', muxer: 'image2', demuxer: 'image2', required: true },
    { name: 'PGM (Portable GrayMap)', encoder: 'pgm', decoder: 'pgm', codec: 'pgm', ext: 'pgm', muxer: 'image2', demuxer: 'image2', required: true },
    { name: 'PPM (Portable PixMap)', encoder: 'ppm', decoder: 'ppm', codec: 'ppm', ext: 'ppm', muxer: 'image2', demuxer: 'image2', required: true },
    { name: 'PCX', encoder: 'pcx', decoder: 'pcx', codec: 'pcx', ext: 'pcx', muxer: 'image2', demuxer: 'image2', required: true },
    { name: 'SGI', encoder: 'sgi', decoder: 'sgi', codec: 'sgi', ext: 'sgi', muxer: 'image2', demuxer: 'image2', required: true },
    { name: 'Sun Raster', encoder: 'sunrast', decoder: 'sunrast', codec: 'sunrast', ext: 'sun', muxer: 'image2', demuxer: 'image2', required: true },
    { name: 'XBM (X Bitmap)', encoder: 'xbm', decoder: 'xbm', codec: 'xbm', ext: 'xbm', muxer: 'image2', demuxer: 'image2', required: true }
];

// ==================================================
// Command execution & Helpers
// ==================================================

function run(command, args) {
    const result = spawnSync(command, args, {
        encoding: 'utf8',
        timeout: TIMEOUT,
        maxBuffer: 8 * 1024 * 1024,
        windowsHide: true
    });

    if (result.error) throw result.error;
    if (result.status !== 0) {
        throw new Error((result.stderr || result.stdout || '').trim() || `Exit code: ${result.status}`);
    }
    return result.stdout || '';
}

function fileExists(file) {
    try {
        return fs.statSync(file).isFile() && fs.statSync(file).size > 0;
    } catch {
        return false;
    }
}

function codecAvailable(listing, name) {
    return listing.split(/\r?\n/).some(line => {
        const match = line.match(/^\s*[A-Z.]{6}\s+(\S+)/);
        return match?.[1] === name;
    });
}

function formatAvailable(listing, name) {
    return listing.split(/\r?\n/).some(line => {
        const match = line.match(/^\s*([D.E]{1,2})\s+(\S+)/);
        if (!match) return false;
        return match[2].split(',').map(s => s.trim()).includes(name);
    });
}

function getListing(type) {
    return run(FFMPEG, ['-hide_banner', `-${type}`]);
}

let encoders = '', decoders = '', muxers = '', demuxers = '';

function featureChecks() {
    console.log('\nFeature listing checks:');
    encoders = getListing('encoders');
    decoders = getListing('decoders');
    muxers = getListing('muxers');
    demuxers = getListing('demuxers');

    for (const label of ['Encoder listing', 'Decoder listing', 'Muxer listing', 'Demuxer listing']) {
        pass(label, 0, { length: formatBytes(getListing(label.toLowerCase().split(' ')[0] + 's').length) });
    }
}

// ==================================================
// FFprobe helpers & Validations
// ==================================================

function probe(file, entries, selector) {
    const output = run(FFPROBE, ['-v', 'error', '-select_streams', selector, '-show_entries', entries, '-of', 'json', file]);
    return JSON.parse(output);
}

function probeAudio(file) {
    const result = probe(file, 'stream=codec_name,sample_rate,channels:format=duration', 'a:0');
    if (!result.streams?.length) throw new Error('No audio stream detected');
    return { ...result.streams[0], duration: Number(result.format?.duration) };
}

function probeImage(file) {
    const result = probe(file, 'stream=codec_name,width,height', 'v:0');
    if (!result.streams?.length) throw new Error('No image stream detected');
    return result.streams[0];
}

function validateDecodedAudio(file) {
    const info = probeAudio(file);
    if (info.codec_name !== 'pcm_s16le') throw new Error(`Expected pcm_s16le, got ${info.codec_name}`);
    if (Number(info.sample_rate) !== SAMPLE_RATE) throw new Error(`Expected ${SAMPLE_RATE} Hz, got ${info.sample_rate}`);
    if (Number(info.channels) !== CHANNELS) throw new Error(`Expected ${CHANNELS} channels, got ${info.channels}`);
    return info;
}

function validateDecodedImage(file) {
    const info = probeImage(file);
    if (info.codec_name !== 'png') throw new Error(`Expected png, got ${info.codec_name}`);
    if (Number(info.width) !== IMAGE_WIDTH || Number(info.height) !== IMAGE_HEIGHT) {
        throw new Error(`Expected ${IMAGE_WIDTH}x${IMAGE_HEIGHT}, got ${info.width}x${info.height}`);
    }
    return info;
}

// ==================================================
// Executable Checks & Source Generators
// ==================================================

function executableChecks() {
    console.log('\nExecutable checks:');
    check('FFmpeg', () => {
        const version = run(FFMPEG, ['-version']);
        return { version: version.split(/\r?\n/)[0].replace('ffmpeg version ', '') };
    });
    check('FFprobe', () => {
        const version = run(FFPROBE, ['-version']);
        return { version: version.split(/\r?\n/)[0].replace('ffprobe version ', '') };
    });
}

function generateSourceAudio() {
    const source = path.join(WORKDIR, 'source.wav');
    check('Generate source audio', () => {
        run(FFMPEG, [
            '-nostdin', '-y', '-hide_banner', '-loglevel', 'error', '-xerror',
            '-f', 'lavfi', '-i', `sine=frequency=1000:sample_rate=${SAMPLE_RATE}:duration=${DURATION}`,
            '-ac', String(CHANNELS), '-ar', String(SAMPLE_RATE), '-c:a', 'pcm_s16le', source
        ]);
        if (!fileExists(source)) throw new Error('Source WAV not generated');
        validateDecodedAudio(source);
        return { size: formatBytes(fs.statSync(source).size) };
    });
    return source;
}

function generateSourceImage() {
    const source = path.join(WORKDIR, 'source.ppm');
    check('Generate source image', () => {
        run(FFMPEG, [
            '-nostdin', '-y', '-hide_banner', '-loglevel', 'error', '-xerror',
            '-f', 'lavfi', '-i', `color=c=blue:s=${IMAGE_WIDTH}x${IMAGE_HEIGHT}`,
            '-frames:v', '1', '-vf', 'format=rgb24', '-c:v', 'ppm', '-f', 'image2', source
        ]);
        if (!fileExists(source)) throw new Error('Source PPM not generated');
        return { size: formatBytes(fs.statSync(source).size), dimensions: `${IMAGE_WIDTH}x${IMAGE_HEIGHT}` };
    });
    return source;
}

// ==================================================
// Format Tests
// ==================================================

function testAudioFormats(source) {
    console.log('\nAudio format tests:');
    for (const format of audioFormats) {
        const label = `Audio: ${format.name}`;
        const requirements = [
            [codecAvailable(encoders, format.encoder), format.encoder, 'Encoder'],
            [codecAvailable(decoders, format.decoder), format.decoder, 'Decoder'],
            [formatAvailable(muxers, format.muxer), format.muxer, 'Muxer'],
            [formatAvailable(demuxers, format.demuxer), format.demuxer, 'Demuxer']
        ];

        const missing = requirements.find(([available]) => !available);
        if (missing) {
            const reason = `${missing[2]} unavailable: ${missing[1]}`;
            if (format.required) check(label, () => { throw new Error(reason); });
            else skip(label, reason);
            continue;
        }

        const output = path.join(WORKDIR, `audio-${format.name}.${format.ext}`);
        const decoded = path.join(WORKDIR, `audio-${format.name}-decoded.wav`);

        check(label, () => {
            run(FFMPEG, ['-nostdin', '-y', '-hide_banner', '-loglevel', 'error', '-xerror', '-i', source, '-map', '0:a:0', '-c:a', format.encoder, '-f', format.muxer, output]);
            if (!fileExists(output)) throw new Error('Encoded audio missing or empty');

            const info = probeAudio(output);
            if (info.codec_name !== format.codec) throw new Error(`Expected ${format.codec}, got ${info.codec_name}`);

            run(FFMPEG, ['-nostdin', '-y', '-hide_banner', '-loglevel', 'error', '-xerror', '-i', output, '-map', '0:a:0', '-c:a', 'pcm_s16le', '-ar', String(SAMPLE_RATE), '-ac', String(CHANNELS), decoded]);
            if (!fileExists(decoded)) throw new Error('Decoded WAV missing or empty');
            validateDecodedAudio(decoded);

            return { size: formatBytes(fs.statSync(output).size), codec: info.codec_name, sr: info.sample_rate };
        });
    }
}

function testImageFormats(source) {
    console.log('\nImage format tests:');
    for (const format of imageFormats) {
        const label = `Image: ${format.name}`;
        const requirements = [
            [codecAvailable(encoders, format.encoder), format.encoder, 'Encoder'],
            [codecAvailable(decoders, format.decoder), format.decoder, 'Decoder'],
            [formatAvailable(muxers, format.muxer), format.muxer, 'Muxer'],
            [formatAvailable(demuxers, format.demuxer), format.demuxer, 'Demuxer']
        ];

        const missing = requirements.find(([available]) => !available);
        if (missing) {
            const reason = `${missing[2]} unavailable: ${missing[1]}`;
            if (format.required) check(label, () => { throw new Error(reason); });
            else skip(label, reason);
            continue;
        }

        const output = path.join(WORKDIR, `image-${format.name}.${format.ext}`);
        const decoded = path.join(WORKDIR, `image-${format.name}-decoded.png`);

        check(label, () => {
            run(FFMPEG, ['-nostdin', '-y', '-hide_banner', '-loglevel', 'error', '-xerror', '-i', source, '-map', '0:v:0', '-frames:v', '1', '-c:v', format.encoder, '-f', format.muxer, output]);
            if (!fileExists(output)) throw new Error('Encoded image missing or empty');

            const info = probeImage(output);
            if (info.codec_name !== format.codec) throw new Error(`Expected ${format.codec}, got ${info.codec_name}`);

            run(FFMPEG, ['-nostdin', '-y', '-hide_banner', '-loglevel', 'error', '-xerror', '-i', output, '-map', '0:v:0', '-frames:v', '1', '-c:v', 'png', '-f', 'image2', decoded]);
            if (!fileExists(decoded)) throw new Error('Decoded PNG missing or empty');
            validateDecodedImage(decoded);

            return { size: formatBytes(fs.statSync(output).size), res: `${info.width}x${info.height}` };
        });
    }
}

// ==================================================
// Main
// ==================================================

try {
    console.log('========================================');
    console.log(' FFmpeg Audio/Image Detailed Runtime Test');
    console.log('========================================');
    console.log(`Platform: ${process.platform} ${process.arch} | Node.js: ${process.version}`);
    console.log(`Temp Dir: ${WORKDIR}`);

    executableChecks();
    featureChecks();

    const sourceAudio = generateSourceAudio();
    const sourceImage = generateSourceImage();

    testAudioFormats(sourceAudio);
    testImageFormats(sourceImage);

} catch (error) {
    console.error('\nFATAL:', error.message);
    failed++;
} finally {
    fs.rmSync(WORKDIR, { recursive: true, force: true });

    console.log('\n========================================');
    console.log(' Detailed Report Summary');
    console.log('========================================');

    for (const res of results) {
        const durationStr = res.durationMs !== undefined ? ` [${res.durationMs}ms]` : '';
        const detailStr = res.details && Object.keys(res.details).length > 0 
            ? ` -> ${JSON.stringify(res.details)}` 
            : '';
        const errStr = res.error ? ` (${res.error})` : '';
        
        console.log(`${res.label.padEnd(24)} | ${res.status}${durationStr}${detailStr}${errStr}`);
    }

    console.log('----------------------------------------');
    console.log(`Passed:  ${passed}`);
    console.log(`Failed:  ${failed}`);
    console.log(`Skipped: ${skipped}`);
    console.log(`Total:   ${passed + failed + skipped}`);
    console.log('========================================');

    process.exitCode = failed > 0 ? 1 : 0;
}