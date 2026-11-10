package com.cyberhats;

import com.cyberfarm.client.renderer.DroneRenderer;
import com.cyberfarm.drone.DroneTask;
import com.cyberfarm.entity.DroneEntity;
import com.cyberfarm.registry.ModEntities;
import com.mojang.blaze3d.vertex.PoseStack;
import com.mojang.math.Axis;

import net.minecraft.client.Minecraft;
import net.minecraft.client.model.EntityModel;
import net.minecraft.client.renderer.MultiBufferSource;
import net.minecraft.client.renderer.entity.layers.RenderLayer;
import net.minecraft.client.renderer.texture.OverlayTexture;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.item.ItemDisplayContext;
import net.minecraft.world.item.ItemStack;
import net.minecraftforge.client.event.EntityRenderersEvent;
import net.minecraftforge.client.event.RenderLivingEvent;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.eventbus.api.IEventBus;

/** Draws the hat a drone wears. On players vanilla already draws whatever item sits in the head slot. */
public final class CyberHatsClient {
    /**
     * Where the hat's bottom stands, in pixels from the drone body's pivot (y down): on the tank, whose top is at -3,
     * just over the rotors' plane at -3.2. The Laser and the Seed Tank end at -3 too; only the Sprayer's canister
     * rises beside the tank, to -4, so over it the hat sits higher. No hat model goes below its own bottom
     * (tools/hats.py checks it), so a hat touches nothing in any pose or combination of modules.
     */
    private static final float SEAT = -3.3F, SEAT_OVER_SPRAYER = -4.1F;
    /** Pixels on the drone per model unit: a hat's 15-unit crown is a little wider than the tank and its band. */
    private static final float SIZE = 0.27F;

    private CyberHatsClient() {}

    static void init(IEventBus modBus) {
        modBus.addListener(CyberHatsClient::addHatLayer);
        MinecraftForge.EVENT_BUS.addListener(CyberHatsClient::hideAntenna);
    }

    /** The hat takes the antenna's place. Every drone shares the model, so this is set again before each one is drawn. */
    private static void hideAntenna(RenderLivingEvent.Pre<?, ?> event) {
        if (event.getRenderer() instanceof DroneRenderer renderer) {
            renderer.model().root().getChild("antenna").visible = event.getEntity().getItemBySlot(EquipmentSlot.HEAD).isEmpty();
        }
    }

    private static void addHatLayer(EntityRenderersEvent.AddLayers event) {
        DroneRenderer renderer = event.getRenderer(ModEntities.DRONE.get());
        if (renderer == null) {
            return;
        }
        renderer.addLayer(new RenderLayer<DroneEntity, EntityModel<DroneEntity>>(renderer) {
            @Override
            public void render(PoseStack pose, MultiBufferSource buffers, int light, DroneEntity drone, float limbSwing,
                    float limbSwingAmount, float partialTick, float ageInTicks, float netHeadYaw, float headPitch) {
                ItemStack hat = drone.getItemBySlot(EquipmentSlot.HEAD);
                if (hat.isEmpty()) {
                    return;
                }
                pose.pushPose();
                // The body's pose, so the hat hovers and sways with it
                renderer.model().translateToTank(pose);
                float seat = (drone.getTaskMask() & DroneTask.FERTILIZE.bit()) != 0 ? SEAT_OVER_SPRAYER : SEAT;
                // An item model is drawn around its middle, 8 units above the hat's bottom
                pose.translate(0.0F, (seat - 8.0F * SIZE) / 16.0F, 0.0F);
                // Model space is upside down; turned as vanilla turns a head item, the model's north faces forward
                pose.mulPose(Axis.YP.rotationDegrees(180.0F));
                pose.scale(SIZE, -SIZE, -SIZE);
                Minecraft.getInstance().getItemRenderer().renderStatic(drone, hat, ItemDisplayContext.NONE, false, pose, buffers,
                        drone.level(), light, OverlayTexture.NO_OVERLAY, drone.getId());
                pose.popPose();
            }
        });
    }
}
