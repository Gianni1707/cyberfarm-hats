package com.cyberhats;

import java.io.Reader;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.joml.Matrix3f;
import org.joml.Matrix4f;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.mojang.blaze3d.vertex.PoseStack;
import com.mojang.blaze3d.vertex.VertexConsumer;
import com.mojang.math.Axis;

import net.minecraft.Util;
import net.minecraft.client.Minecraft;
import net.minecraft.client.renderer.BlockEntityWithoutLevelRenderer;
import net.minecraft.client.renderer.LightTexture;
import net.minecraft.client.renderer.MultiBufferSource;
import net.minecraft.client.renderer.RenderType;
import net.minecraft.client.renderer.texture.TextureAtlasSprite;
import net.minecraft.client.resources.model.BakedModel;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.packs.resources.ResourceManager;
import net.minecraft.util.Mth;
import net.minecraft.world.inventory.InventoryMenu;
import net.minecraft.world.item.ItemDisplayContext;
import net.minecraft.world.item.ItemStack;
import net.minecraftforge.client.event.ModelEvent;
import net.minecraftforge.client.event.RegisterClientReloadListenersEvent;
import net.minecraftforge.registries.ForgeRegistries;

/**
 * Draws a hat that has moving parts (a propeller, a tassel, a jester's points) wherever it shows: on a head, on a drone,
 * in a frame or a slot. 1.20.1 has no special item models, so the hat's item model is builtin/entity and this draws its
 * still model (models/item/NAME_still.json) and then the parts from hat_parts/NAME.json, which tools/hats.py writes:
 * quads around a pivot, and their motions (see Hat.move there).
 */
public final class HatRenderer extends BlockEntityWithoutLevelRenderer {
    private static HatRenderer instance;
    private final Map<ResourceLocation, List<Part>> parts = new HashMap<>();

    private record Motion(String kind, String axis, float amount, float period, float phase) {}

    private record Part(float[] pivot, boolean bright, List<Motion> motions, List<float[]> quads) {}

    private HatRenderer() {
        super(Minecraft.getInstance().getBlockEntityRenderDispatcher(), Minecraft.getInstance().getEntityModels());
    }

    static HatRenderer get() {
        if (instance == null) {
            instance = new HatRenderer();
        }
        return instance;
    }

    /** The still models of the moving hats, which nothing else asks the game to load. */
    static void registerStillModels(ModelEvent.RegisterAdditional event) {
        Minecraft.getInstance().getResourceManager()
                .listResources("models/item", path -> path.getNamespace().equals(CyberHats.MODID) && path.getPath().endsWith("_still.json"))
                .keySet().forEach(path -> event.register(new ResourceLocation(path.getNamespace(),
                        path.getPath().substring("models/".length(), path.getPath().length() - ".json".length()))));
    }

    static void registerReload(RegisterClientReloadListenersEvent event) {
        event.registerReloadListener(get());
    }

    @Override
    public void onResourceManagerReload(ResourceManager resources) {
        parts.clear();
    }

    @Override
    public void renderByItem(ItemStack stack, ItemDisplayContext context, PoseStack pose, MultiBufferSource buffers, int light, int overlay) {
        ResourceLocation id = ForgeRegistries.ITEMS.getKey(stack.getItem());
        if (id == null) {
            return;
        }
        Minecraft minecraft = Minecraft.getInstance();
        VertexConsumer buffer = buffers.getBuffer(RenderType.entityCutout(InventoryMenu.BLOCK_ATLAS));
        BakedModel still = minecraft.getModelManager().getModel(new ResourceLocation(id.getNamespace(), "item/" + id.getPath() + "_still"));
        minecraft.getItemRenderer().renderModelLists(still, stack, light, overlay, pose, buffer);
        TextureAtlasSprite sprite = minecraft.getTextureAtlas(InventoryMenu.BLOCK_ATLAS).apply(new ResourceLocation(id.getNamespace(), "item/" + id.getPath()));
        float seconds = (Util.getMillis() % 3_600_000L) / 1000.0F;
        for (Part part : parts.computeIfAbsent(id, HatRenderer::load)) {
            pose.pushPose();
            // Model units to the item's block space, where the still model is drawn too
            pose.scale(1.0F / 16.0F, 1.0F / 16.0F, 1.0F / 16.0F);
            for (Motion motion : part.motions()) {
                move(pose, part.pivot(), motion, seconds);
            }
            Matrix4f matrix = pose.last().pose();
            Matrix3f normal = pose.last().normal();
            int shown = part.bright() ? LightTexture.FULL_BRIGHT : light;
            for (float[] quad : part.quads()) {
                for (int c = 0; c < 20; c += 5) {
                    buffer.vertex(matrix, quad[c], quad[c + 1], quad[c + 2]).color(1.0F, 1.0F, 1.0F, 1.0F)
                            .uv(sprite.getU(quad[c + 3] * 16.0F), sprite.getV(quad[c + 4] * 16.0F)).overlayCoords(overlay).uv2(shown)
                            .normal(normal, quad[20], quad[21], quad[22]).endVertex();
                }
            }
            pose.popPose();
        }
    }

    private static void move(PoseStack pose, float[] pivot, Motion motion, float seconds) {
        float cycle = seconds / motion.period() + motion.phase();
        float wave = Mth.sin(cycle * Mth.TWO_PI);
        Axis around = switch (motion.axis()) {
            case "x" -> Axis.XP;
            case "z" -> Axis.ZP;
            default -> Axis.YP;
        };
        boolean x = motion.axis().equals("x"), y = motion.axis().equals("y"), z = motion.axis().equals("z");
        switch (motion.kind()) {
            case "swing" -> pose.rotateAround(around.rotationDegrees(motion.amount() * wave), pivot[0], pivot[1], pivot[2]);
            case "spin" -> pose.rotateAround(around.rotationDegrees(360.0F * Mth.frac(cycle)), pivot[0], pivot[1], pivot[2]);
            case "bob" -> pose.translate(x ? motion.amount() * wave : 0.0F, y ? motion.amount() * wave : 0.0F, z ? motion.amount() * wave : 0.0F);
            case "blink" -> {
                // Shut for a moment once a period
                float open = Mth.frac(cycle) < 0.05F ? 0.1F : 1.0F;
                pose.translate(pivot[0], pivot[1], pivot[2]);
                pose.scale(x ? open : 1.0F, y ? open : 1.0F, z ? open : 1.0F);
                pose.translate(-pivot[0], -pivot[1], -pivot[2]);
            }
            default -> {}
        }
    }

    private static List<Part> load(ResourceLocation hat) {
        List<Part> loaded = new ArrayList<>();
        ResourceLocation file = new ResourceLocation(hat.getNamespace(), "hat_parts/" + hat.getPath() + ".json");
        Minecraft.getInstance().getResourceManager().getResource(file).ifPresent(resource -> {
            try (Reader reader = resource.openAsReader()) {
                for (JsonElement element : JsonParser.parseReader(reader).getAsJsonObject().getAsJsonArray("parts")) {
                    JsonObject part = element.getAsJsonObject();
                    List<Motion> motions = new ArrayList<>();
                    for (JsonElement m : part.getAsJsonArray("motions")) {
                        JsonObject motion = m.getAsJsonObject();
                        motions.add(new Motion(motion.get("kind").getAsString(), motion.get("axis").getAsString(), motion.get("amount").getAsFloat(),
                                motion.get("period").getAsFloat(), motion.get("phase").getAsFloat()));
                    }
                    List<float[]> quads = new ArrayList<>();
                    for (JsonElement q : part.getAsJsonArray("quads")) {
                        quads.add(floats(q.getAsJsonArray()));
                    }
                    loaded.add(new Part(floats(part.getAsJsonArray("pivot")), part.get("bright").getAsBoolean(), motions, quads));
                }
            } catch (Exception e) {
                CyberHats.LOGGER.error("Could not read the moving parts of {}", hat, e);
            }
        });
        return loaded;
    }

    private static float[] floats(JsonArray array) {
        float[] values = new float[array.size()];
        for (int i = 0; i < values.length; i++) {
            values[i] = array.get(i).getAsFloat();
        }
        return values;
    }
}
