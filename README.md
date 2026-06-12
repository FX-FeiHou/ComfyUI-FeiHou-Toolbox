# comfyui-feihou-toolbox

FeiHou custom nodes for ComfyUI.

## Nodes

- `SCAIL2ColoredMaskV2` / `Create SCAIL-2 Colored Mask V2`

This node is modified from ComfyUI's built-in `SCAIL2ColoredMask` node and
keeps the original node id/display name for workflow compatibility. It adds
`prefix_image_mask`, configurable render device handling, and warnings for
empty prefix SAM3 track data.

- `AutoRefCollage` / `多参图像自动拼接`

Uses SAM3/SAM3.1 `MODEL` and `CLIP` outputs from `CheckpointLoaderSimple` to
extract 2-4 reference people from image inputs with the node's internal prompt,
then automatically composes portrait, square, or landscape collages from the
requested output width and height. Outputs the RGB collage image and an alpha
mask.

## License

GPL-3.0. See `LICENSE`.
