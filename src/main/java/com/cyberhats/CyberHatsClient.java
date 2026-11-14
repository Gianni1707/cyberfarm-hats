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
import net.minecraftforge.client.event.RenderPlayerEvent;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.eventbus.api.EventPriority;
import net.minecraftforge.eventbus.api.IEventBus;
import net.minecraftforge.fml.ModList;

import java.util.IdentityHashMap;
import java.util.Map;

import net.minecraft.world.entity.player.Player;

/** Draws the hat a drone wears, and the one in the Hat slot on the player. Vanilla draws one in the helmet slot. */
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

    /** The helmets taken off for the time a player is drawn with their cosmetic hat. */
    private static final Map<Player, ItemStack> HELMETS = new IdentityHashMap<>();

    static void init(IEventBus modBus) {
        modBus.addListener(CyberHatsClient::addHatLayer);
        MinecraftForge.EVENT_BUS.addListener(CyberHatsClient::hideAntenna);
        MinecraftForge.EVENT_BUS.addListener(HatSlotWidgets::addTo);
        // Last of all, so a render another mod cancels never leaves the helmet swapped
        MinecraftForge.EVENT_BUS.addListener(EventPriority.LOWEST, CyberHatsClient::wearCosmeticHat);
        MinecraftForge.EVENT_BUS.addListener(CyberHatsClient::restoreHelmet);
    }

    /** A player's Hat slot, as the server sent it. */
    static void applySync(int entity, HatSlot.Worn worn) {
        if (Minecraft.getInstance().level != null && Minecraft.getInstance().level.getEntity(entity) instanceof Player player) {
            HatSlot.setWorn(player, worn);
        }
    }

    /**
     * 1.20.1 draws the helmet and a worn head item straight from the player's armor, so for the time the player is drawn
     * the hat from the Hat slot (or Curios' head slot) takes the helmet's place on this client; the next event puts the
     * helmet back.
     */
    private static void wearCosmeticHat(RenderPlayerEvent.Pre event) {
        Player player = event.getEntity();
        ItemStack hat = HatSlot.ownSlot() ? HatSlot.shownHat(player)
                : ModList.get().isLoaded(CuriosHats.MODID) ? CuriosHats.shownHat(player) : ItemStack.EMPTY;
        if (!hat.isEmpty()) {
            HELMETS.put(player, player.getInventory().armor.get(EquipmentSlot.HEAD.getIndex()));
            player.getInventory().armor.set(EquipmentSlot.HEAD.getIndex(), hat);
        }
    }

    private static void restoreHelmet(RenderPlayerEvent.Post event) {
        ItemStack helmet = HELMETS.remove(event.getEntity());
        if (helmet != null) {
            event.getEntity().getInventory().armor.set(EquipmentSlot.HEAD.getIndex(), helmet);
        }
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
