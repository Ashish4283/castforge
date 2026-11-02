"""Stand-in for the Gemini step: a background image, room tone and two dialogue lines, made locally
(SDXL-Lightning + Kokoro TTS, both free). The real app will use the user's Gemini assets instead.

    python generate/make_test_scene_assets.py out_dir
"""
import os
import sys

import numpy as np
import soundfile as sf

out = sys.argv[1]
os.makedirs(out, exist_ok=True)

# --- dialogue (Kokoro, 24 kHz) -----------------------------------------------------------------
from kokoro import KPipeline  # noqa: E402

pipe = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
LINES = {
    "line1_maya": ("af_heart", "Oh, there you are! I was starting to think you got lost."),
    "line2_tom": ("am_michael", "Sorry, the bus was late again. Did you already order coffee?"),
}
for name, (voice, text) in LINES.items():
    audio = np.concatenate([a for _, _, a in pipe(text, voice=voice)])
    sf.write(os.path.join(out, f"{name}.wav"), audio, 24000, subtype="PCM_16")
    print("saved", name, f"{len(audio) / 24000:.1f}s", flush=True)

# --- room tone: soft filtered noise -------------------------------------------------------------
rng = np.random.default_rng(1)
n = 24000 * 20
noise = np.cumsum(rng.normal(size=n))
noise -= np.convolve(noise, np.ones(2400) / 2400, mode="same")
noise = 0.03 * noise / np.abs(noise).max()
sf.write(os.path.join(out, "ambience.wav"), noise.astype(np.float32), 24000, subtype="PCM_16")

# --- background (SDXL-Lightning) ----------------------------------------------------------------
import torch  # noqa: E402
from diffusers import EulerDiscreteScheduler, StableDiffusionXLPipeline, UNet2DConditionModel  # noqa: E402
from huggingface_hub import hf_hub_download  # noqa: E402
from safetensors.torch import load_file  # noqa: E402

BASE = "stabilityai/stable-diffusion-xl-base-1.0"
unet = UNet2DConditionModel.from_config(BASE, subfolder="unet").to(torch.float16)
unet.load_state_dict(load_file(hf_hub_download("ByteDance/SDXL-Lightning", "sdxl_lightning_4step_unet.safetensors")))
sd = StableDiffusionXLPipeline.from_pretrained(BASE, unet=unet, torch_dtype=torch.float16, variant="fp16")
sd.scheduler = EulerDiscreteScheduler.from_config(sd.scheduler.config, timestep_spacing="trailing")
sd.enable_model_cpu_offload()
img = sd("interior of a cozy empty coffee shop, eye level view from the middle of the room, wooden floor, "
         "counter and shelves in the back, warm daylight from windows, no people, wide angle, photorealistic",
         num_inference_steps=4, guidance_scale=0, width=1344, height=768,
         generator=torch.Generator("cuda").manual_seed(7)).images[0]
img.resize((1280, 720)).save(os.path.join(out, "background.png"))
print("saved background", flush=True)
