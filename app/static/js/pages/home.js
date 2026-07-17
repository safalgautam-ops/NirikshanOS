// Loads the Rive-based hero animation and keeps the floating scene labels
// in sync with whichever stage of the animation is currently on screen.
//
// The .riv file only stores generic placeholder image names - Rive's
// assetLoader callback intercepts every one of those references and swaps
// in our own PNGs (see the `files` map below). There's no "which scene is
// showing" event from the state machine either, so `watch()` samples a
// single pixel per scene every 80ms and treats the darkest match as active
// - the sample points are tuned to land on a patch of the animation that
// changes brightness distinctly between scenes.
import { RiveLib } from "/static/vendor/rive/rive.js";

const stage = document.getElementById("hero-animation");

if (stage) {
    const base = stage.dataset.base;
    const imgBase = stage.dataset.imgBase;
    const canvas = stage.querySelector("canvas");

    RiveLib.RuntimeLoader.setWasmUrl(`${base}/rive.wasm`);

    const files = {
        "pasted_file-4724918.png": "tile_main.png",
        "1-4724938.png": "tile_1.png",
        "2-4724939.png": "tile_2.png",
        "3-4724940.png": "tile_3.png",
        "4-4724942.png": "tile_4.png",
        "5-4724943.png": "tile_5.png",
        "pasted_file-4727651.png": "label_1.png",
        "pasted_file-4727731.png": "label_2.png",
        "pasted_file-4727671.png": "label_3.png",
        "pasted_file-4728189.png": "label_4.png",
        "pasted_file-4727677.png": "label_5.png",
    };

    // [name, description, side, verticalPercent, samplePoint, accentColor]
    const scenes = [
        ["INTAKE", "secure evidence upload", "left", 29.9, [0.108, 0.299], "#6948ff"],
        ["ANALYZE", "modular analysis pipeline", "right", 40.7, [0.823, 0.407], "#1edc7c"],
        ["INVESTIGATE", "case workspace", "left", 50, [0.108, 0.5], "#7b46ff"],
        ["FORENSICS", "chain-of-custody & audit trail", "right", 59.8, [0.814, 0.598], "#ff6c12"],
        ["REPORT", "findings & timeline", "left", 69.9, [0.108, 0.699], "#20cbd8"],
    ];

    const items = scenes.map(([name, desc, side, top, , color]) => {
        const el = document.createElement("div");
        el.className = `hero-anim-item ${side}`;
        el.style.cssText = `top:${top}%;--c:${color}`;
        el.innerHTML = `<span class="hero-anim-line"></span><span class="hero-anim-badge">${name}</span><span class="hero-anim-desc">${desc}</span>`;
        stage.appendChild(el);
        return el;
    });

    const rive = new RiveLib.Rive({
        src: `${base}/hero-animation.riv`,
        canvas,
        autoplay: false,
        stateMachines: "State Machine 1",
        assetLoader: (asset) => {
            const filename = files[asset.uniqueFilename];
            if (!filename) return false;
            fetch(`${imgBase}/${filename}`)
                .then((res) => res.arrayBuffer())
                .then((buf) => RiveLib.decodeImage(new Uint8Array(buf)))
                .then((image) => {
                    asset.setRenderImage(image);
                    image.unref();
                });
            return true;
        },
        onLoad: () => {
            rive.resizeDrawingSurfaceToCanvas();
            rive.play();
            watchActiveScene();
        },
    });

    function watchActiveScene() {
        const ctx = canvas.getContext("2d");
        const sample = ([px, py]) => {
            const [r, g, b] = ctx.getImageData(canvas.width * px, canvas.height * py, 1, 1).data;
            return r + g + b;
        };
        let lastActive = -1;
        setInterval(() => {
            let darkest = Infinity;
            let activeIndex = -1;
            scenes.forEach((scene, i) => {
                const value = sample(scene[4]);
                if (value < darkest) {
                    darkest = value;
                    activeIndex = i;
                }
            });
            if (darkest < 430 && activeIndex !== lastActive) {
                items.forEach((el, i) => el.classList.toggle("active", i === activeIndex));
                lastActive = activeIndex;
            }
        }, 80);
    }
}
