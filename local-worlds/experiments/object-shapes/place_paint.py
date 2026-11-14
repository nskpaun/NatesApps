import sys, os, time
sys.path.insert(0, os.getcwd())
import chisel_ring as C
from mflux.models.z_image.variants.controlnet.control_types import ControlSpec, ControlType
from mflux.models.z_image.variants.controlnet.z_image_turbo_controlnet import ZImageTurboControlnet
out = sys.argv[1]
C.speed_patches(); C.painter_patches()
model = ZImageTurboControlnet(quantize=8)
for k in sys.argv[2:]:
    t = time.time()
    img = model.generate_image(seed=7, prompt="interior photo, Mid-Century Modern garage. In view: a cream 1930s antique car on a low display platform.", controlnet_strength=1.0, num_inference_steps=8, width=768, height=576,
                               controls=[ControlSpec(type=ControlType.depth, image_path=f"{out}/depth_{int(k):02d}.png", strength=0.9)])
    img.save(f"{out}/paint_{int(k):02d}.png"); print(k, round(time.time() - t), "s", flush=True)
