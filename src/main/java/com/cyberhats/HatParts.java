package com.cyberhats;

import java.util.List;
import java.util.function.Consumer;

import org.joml.Vector3f;
import org.joml.Vector3fc;
import org.jspecify.annotations.Nullable;

import com.mojang.blaze3d.vertex.PoseStack;
import com.mojang.math.Axis;
import com.mojang.serialization.Codec;
import com.mojang.serialization.MapCodec;
import com.mojang.serialization.codecs.RecordCodecBuilder;

import net.minecraft.client.renderer.SubmitNodeCollector;
import net.minecraft.client.renderer.rendertype.RenderTypes;
import net.minecraft.client.renderer.special.SpecialModelRenderer;
import net.minecraft.resources.Identifier;
import net.minecraft.util.ExtraCodecs;
import net.minecraft.util.LightCoordsUtil;
import net.minecraft.util.Mth;
import net.minecraft.util.Util;
import net.minecraft.world.item.ItemStack;

/**
 * The moving parts of a hat (a propeller, a tassel, a jester's points), drawn over its still model wherever the hat
 * is shown: on a head, on a drone, in a frame or a slot. tools/hats.py writes them into the hat's item definition as
 * quads around a pivot, with their motions; its moved() moves them the same way, to check they clear the hat's bottom.
 */
public record HatParts(Identifier texture, List<Part> parts) implements SpecialModelRenderer<Float> {
    public static final Identifier TYPE = CyberHats.id("hat_parts");

    /** One motion around the part's pivot; see Hat.move in tools/hats.py. */
    record Motion(String kind, String axis, float amount, float period, float phase) {
        static final Codec<Motion> CODEC = RecordCodecBuilder.create(i -> i.group(
                Codec.STRING.fieldOf("kind").forGetter(Motion::kind),
                Codec.STRING.fieldOf("axis").forGetter(Motion::axis),
                Codec.FLOAT.fieldOf("amount").forGetter(Motion::amount),
                Codec.FLOAT.fieldOf("period").forGetter(Motion::period),
                Codec.FLOAT.optionalFieldOf("phase", 0.0F).forGetter(Motion::phase)).apply(i, Motion::new));

        void apply(PoseStack pose, Vector3fc pivot, float seconds) {
            float cycle = seconds / period + phase;
            float wave = Mth.sin(cycle * Mth.TWO_PI);
            Axis around = switch (axis) {
                case "x" -> Axis.XP;
                case "z" -> Axis.ZP;
                default -> Axis.YP;
            };
            switch (kind) {
                case "swing" -> pose.rotateAround(around.rotationDegrees(amount * wave), pivot.x(), pivot.y(), pivot.z());
                case "spin" -> pose.rotateAround(around.rotationDegrees(360.0F * Mth.frac(cycle)), pivot.x(), pivot.y(), pivot.z());
                case "bob" -> pose.translate(axis.equals("x") ? amount * wave : 0.0F, axis.equals("y") ? amount * wave : 0.0F,
                        axis.equals("z") ? amount * wave : 0.0F);
                case "blink" -> {
                    // Shut for a moment once a period
                    float open = Mth.frac(cycle) < 0.05F ? 0.1F : 1.0F;
                    pose.translate(pivot.x(), pivot.y(), pivot.z());
                    pose.scale(axis.equals("x") ? open : 1.0F, axis.equals("y") ? open : 1.0F, axis.equals("z") ? open : 1.0F);
                    pose.translate(-pivot.x(), -pivot.y(), -pivot.z());
                }
                default -> {}
            }
        }
    }

    /** Quads of 23 numbers: four corners of x, y, z (model units), u, v; then the face's normal. */
    record Part(Vector3fc pivot, boolean bright, List<Motion> motions, List<List<Float>> quads) {
        static final Codec<Part> CODEC = RecordCodecBuilder.create(i -> i.group(
                ExtraCodecs.VECTOR3F.fieldOf("pivot").forGetter(Part::pivot),
                Codec.BOOL.optionalFieldOf("bright", false).forGetter(Part::bright),
                Motion.CODEC.listOf().fieldOf("motions").forGetter(Part::motions),
                Codec.FLOAT.listOf(23, 23).listOf().fieldOf("quads").forGetter(Part::quads)).apply(i, Part::new));
    }

    public record Unbaked(Identifier texture, List<Part> parts) implements SpecialModelRenderer.Unbaked<Float> {
        public static final MapCodec<Unbaked> MAP_CODEC = RecordCodecBuilder.mapCodec(i -> i.group(
                Identifier.CODEC.fieldOf("texture").forGetter(Unbaked::texture),
                Part.CODEC.listOf().fieldOf("parts").forGetter(Unbaked::parts)).apply(i, Unbaked::new));

        @Override
        public SpecialModelRenderer<Float> bake(BakingContext context) {
            return new HatParts(texture, parts);
        }

        @Override
        public MapCodec<Unbaked> type() {
            return MAP_CODEC;
        }
    }

    /** The time in seconds; a new one each frame also tells the inventory to draw the hat again. */
    @Override
    public Float extractArgument(ItemStack stack) {
        return (Util.getMillis() % 3_600_000L) / 1000.0F;
    }

    @Override
    public void submit(@Nullable Float time, PoseStack pose, SubmitNodeCollector collector, int light, int overlay, boolean hasFoil, int outlineColor) {
        float seconds = time == null ? 0.0F : time;
        for (Part part : parts) {
            pose.pushPose();
            // Model units to the item's block space, where the still model is drawn too
            pose.scale(1.0F / 16.0F, 1.0F / 16.0F, 1.0F / 16.0F);
            for (Motion motion : part.motions()) {
                motion.apply(pose, part.pivot(), seconds);
            }
            int shown = part.bright() ? LightCoordsUtil.FULL_BRIGHT : light;
            collector.submitCustomGeometry(pose, RenderTypes.entityCutout(texture), (at, buffer) -> {
                for (List<Float> quad : part.quads()) {
                    for (int corner = 0; corner < 4; corner++) {
                        int c = corner * 5;
                        buffer.addVertex(at, quad.get(c), quad.get(c + 1), quad.get(c + 2)).setColor(-1).setUv(quad.get(c + 3), quad.get(c + 4))
                                .setOverlay(overlay).setLight(shown).setNormal(at, quad.get(20), quad.get(21), quad.get(22));
                    }
                }
            });
            pose.popPose();
        }
    }

    @Override
    public void getExtents(Consumer<Vector3fc> output) {
        for (Part part : parts) {
            for (List<Float> quad : part.quads()) {
                for (int c = 0; c < 20; c += 5) {
                    output.accept(new Vector3f(quad.get(c), quad.get(c + 1), quad.get(c + 2)).div(16.0F));
                }
            }
        }
    }
}
