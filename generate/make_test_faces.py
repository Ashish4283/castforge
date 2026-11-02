"""Make fictional front-facing portraits for testing the face stage (SDXL-Lightning, local GPU).

These people do not exist, so the results can be shown in demos.

    python generate/make_test_faces.py out_dir
"""
import os
import sys

import torch
from diffusers import EulerDiscreteScheduler, StableDiffusionXLPipeline, UNet2DConditionModel
from huggingface_hub import hf_hub_download
from safetensors.torch import load_file

out = sys.argv[1]
os.makedirs(out, exist_ok=True)
BASE = "stabilityai/stable-diffusion-xl-base-1.0"
unet = UNet2DConditionModel.from_config(BASE, subfolder="unet").to(torch.float16)
unet.load_state_dict(load_file(hf_hub_download("ByteDance/SDXL-Lightning", "sdxl_lightning_4step_unet.safetensors")))
pipe = StableDiffusionXLPipeline.from_pretrained(BASE, unet=unet, torch_dtype=torch.float16, variant="fp16")
pipe.scheduler = EulerDiscreteScheduler.from_config(pipe.scheduler.config, timestep_spacing="trailing")
pipe.enable_model_cpu_offload()

PEOPLE = {
    "face_woman": "passport style studio photo of a 30 year old woman, looking straight at the camera, neutral "
                  "expression, mouth closed, face centered, even soft front lighting, plain light grey background, "
                  "shoulders visible, sharp focus, natural skin texture, photorealistic",
    "face_man": "passport style studio photo of a 40 year old man with short hair, looking straight at the camera, "
                "neutral expression, mouth closed, face centered, even soft front lighting, plain light grey "
                "background, shoulders visible, sharp focus, natural skin texture, photorealistic",
}
for i, (name, prompt) in enumerate(PEOPLE.items()):
    img = pipe(prompt, num_inference_steps=4, guidance_scale=0, height=1024, width=1024,
               generator=torch.Generator("cuda").manual_seed(1234 + i)).images[0]
    img.save(os.path.join(out, f"{name}.png"))
    print("saved", name, flush=True)
