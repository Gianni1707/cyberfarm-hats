package com.cyberhats;

import com.cyberfarm.client.model.DroneModel;
import com.cyberfarm.client.renderer.DroneRenderState;
import com.cyberfarm.client.renderer.DroneRenderer;
import com.cyberfarm.drone.DroneTask;
import com.cyberfarm.entity.DroneEntity;
import com.cyberfarm.registry.ModEntities;
import com.mojang.blaze3d.vertex.PoseStack;
import com.mojang.math.Axis;

import net.minecraft.client.Minecraft;
import net.minecraft.client.renderer.SubmitNodeCollector;
import net.minecraft.client.renderer.entity.layers.RenderLayer;
import net.minecraft.client.renderer.item.ItemStackRenderState;
import net.minecraft.client.renderer.texture.OverlayTexture;
import net.minecraft.util.context.ContextKey;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.item.ItemDisplayContext;
import net.minecraft.world.item.ItemStack;
import net.neoforged.api.distmarker.Dist;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.fml.common.Mod;
import net.neoforged.neoforge.client.event.EntityRenderersEvent;
import net.neoforged.neoforge.client.renderstate.RegisterRenderStateModifiersEvent;

/** Draws the hat a drone wears. On players vanilla already draws whatever item sits in the head slot. */
@Mod(value = CyberHats.MODID, dist = Dist.CLIENT)
public class CyberHatsClient {
    private static final ContextKey<ItemStackRenderState> HAT = new ContextKey<>(CyberHats.id("drone_hat"));
    /**
     * Where the hat's bottom stands, in pixels from the drone body's pivot (y down): on the tank, whose top is at -3,
     * just over the rotors' plane at -3.2. The Laser and the Seed Tank end at -3 too; only the Sprayer's canister
     * rises beside the tank, to -4, so over it the hat sits higher. No hat model goes below its own bottom
     * (tools/hats.py checks it), so a hat touches nothing in any pose or combination of modules.
     */
    private static final float SEAT = -3.3F, SEAT_OVER_SPRAYER = -4.1F;
    /** Pixels on the drone per model unit: a hat's 15-unit crown is a little wider than the tank and its band. */
    private static final float SIZE = 0.27F;

    public CyberHatsClient(IEventBus modBus) {
        modBus.addListener(CyberHatsClient::extractHat);
        modBus.addListener(CyberHatsClient::addHatLayer);
    }

    private static void extractHat(RegisterRenderStateModifiersEvent event) {
        event.registerEntityModifier(DroneRenderer.class, (DroneEntity drone, DroneRenderState state) -> {
            ItemStack hat = drone.getItemBySlot(EquipmentSlot.HEAD);
            if (!hat.isEmpty()) {
                ItemStackRenderState shown = new ItemStackRenderState();
                // NONE: the bare model, without the transform that fits it to a player's head
                Minecraft.getInstance().getItemModelResolver().updateForLiving(shown, hat, ItemDisplayContext.NONE, drone);
                state.setRenderData(HAT, shown);
                // The hat takes the antenna's place
                state.overrideModelPartVisibility("antenna", false);
            }
        });
    }

    private static void addHatLayer(EntityRenderersEvent.AddLayers event) {
        DroneRenderer renderer = event.getRenderer(ModEntities.DRONE.get());
        if (renderer == null) {
            return;
        }
        renderer.addLayer(new RenderLayer<DroneRenderState, DroneModel>(renderer) {
            @Override
            public void submit(PoseStack pose, SubmitNodeCollector collector, int light, DroneRenderState state, float yRot, float xRot) {
                ItemStackRenderState hat = state.getRenderData(HAT);
                if (hat == null) {
                    return;
                }
                pose.pushPose();
                // The body's pose, so the hat hovers and sways with it
                getParentModel().translateToTank(pose);
                // An item model is drawn around its middle, 8 units above the hat's bottom
                float seat = state.has(DroneTask.FERTILIZE) ? SEAT_OVER_SPRAYER : SEAT;
                pose.translate(0.0F, (seat - 8.0F * SIZE) / 16.0F, 0.0F);
                // Model space is upside down; turned as vanilla turns a head item, the model's north faces forward
                pose.mulPose(Axis.YP.rotationDegrees(180.0F));
                pose.scale(SIZE, -SIZE, -SIZE);
                hat.submit(pose, collector, light, OverlayTexture.NO_OVERLAY, state.outlineColor);
                pose.popPose();
            }
        });
    }
}
