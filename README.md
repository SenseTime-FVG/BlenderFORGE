# BlenderFORGE

**Framework for Optimizing Reactive 3D-Graphics Editing Ability of MLLMs**

[Project Page](https://sensetime-fvg.github.io/BlenderFORGE/) ·
[Paper](website/assets/paper.pdf) ·
[Leaderboard](https://sensetime-fvg.github.io/BlenderFORGE/#results)

BlenderFORGE trains open-weight multimodal agents to edit explicit Blender scenes
through executable Python actions. It connects perturbation-based task generation,
an interactive Blender sandbox with rendered and structured feedback, and
trajectory supervised fine-tuning followed by multi-turn reinforcement learning.

The benchmark covers four editing families, with 9,000 training tasks and 800
test tasks. Qwen3-VL-8B and Qwen3.5-9B agents are compared with their respective
base models and zero-shot model references.

![BlenderFORGE framework](website/assets/images/framework.webp)

## Editing Tasks

| Task | Editing Target |
| --- | --- |
| Placement | Object translation and rotation |
| Shape-Key | Blend-shape coefficients |
| Lighting | Light color and energy |
| Material | Shader parameters |

The project page includes the framework overview, video demonstrations and an
interactive leaderboard with task filters, metric sorting and CSV export.

## Release Checklist

- [ ] Evaluation code.
- [ ] Blender Sandbox code.
- [ ] Model checkpoints on Hugging Face.
- [ ] Datasets on Hugging Face.

## Citation

Bibliographic details will be finalized with the public paper release.

```bibtex
@misc{blenderforge,
  title  = {BlenderFORGE: Framework for Optimizing Reactive
            3D-Graphics Editing Ability of MLLMs},
  author = {TBD},
  year   = {TBD}
}
```

## License

[MIT License](LICENSE).
