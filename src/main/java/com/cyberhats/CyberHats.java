package com.cyberhats;

import java.util.List;
import java.util.Set;
import java.util.stream.Stream;

import com.cyberfarm.entity.DroneEntity;
import com.cyberfarm.registry.ModCreativeTabs;

import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.sounds.SoundSource;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.ShearsItem;
import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.event.BuildCreativeModeTabContentsEvent;
import net.minecraftforge.event.entity.EntityLeaveLevelEvent;
import net.minecraftforge.event.entity.player.PlayerInteractEvent;
import net.minecraftforge.eventbus.api.IEventBus;
import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.fml.javafmlmod.FMLJavaModLoadingContext;
import net.minecraftforge.fml.loading.FMLEnvironment;
import net.minecraftforge.registries.DeferredRegister;
import net.minecraftforge.registries.ForgeRegistries;
import net.minecraftforge.registries.RegistryObject;

/**
 * Hats for players and CyberFarm drones. A hat is an item worn in the head slot, which vanilla draws on players and
 * armor stands; a right click puts it on a drone and shears take it off, and {@link CyberHatsClient} draws it there.
 */
@Mod(CyberHats.MODID)
public class CyberHats {
    public static final String MODID = "cyberhats";

    private static final DeferredRegister<Item> ITEMS = DeferredRegister.create(ForgeRegistries.ITEMS, MODID);
    /** The hats from a game, anime or film: each shows a famous line from it, item.cyberhats.<name>.quote (tools/hats.py). */
    private static final Set<String> QUOTED = Set.of(
            "red_plumber_cap", "green_plumber_cap", "mushroom_cap", "elf_cap", "straw_hat", "cowboy_hat", "baseball_cap",
            "flat_cap", "fedora", "fez", "party_hat", "halo", "chicken_hat", "professor_top_hat", "apprentice_cap",
            "phantom_thief_hat", "trainer_cap", "black_mage_hat");
    /** Every hat. A new one needs its name here and its boxes in tools/hats.py, which writes all its files. */
    public static final List<RegistryObject<HatItem>> HATS = Stream.of(
            "hard_hat", "wizard_hat", "flat_cap", "straw_hat", "elf_cap", "cowboy_hat", "baseball_cap", "top_hat", "goggle_top_hat",
            "red_plumber_cap", "green_plumber_cap", "chef_hat", "crown", "santa_hat", "viking_helmet", "propeller_beanie",
            "pirate_hat", "sombrero", "fedora", "beret", "ushanka", "graduation_cap", "jester_hat", "party_hat", "witch_hat",
            "fez", "mushroom_cap", "halo", "samurai_helmet", "aviator_cap", "captain_hat", "frog_hat", "chicken_hat",
            "professor_top_hat", "time_traveler_top_hat", "phantom_thief_hat", "apprentice_cap", "trainer_cap", "wanderer_hat",
            "black_mage_hat")
            .map(name -> ITEMS.register(name, () -> new HatItem(new Item.Properties().stacksTo(1), QUOTED.contains(name))))
            .toList();

    public CyberHats() {
        IEventBus modBus = FMLJavaModLoadingContext.get().getModEventBus();
        ITEMS.register(modBus);
        modBus.addListener((BuildCreativeModeTabContentsEvent event) -> {
            if (event.getTabKey() == ModCreativeTabs.MAIN.getKey()) {
                HATS.forEach(hat -> event.accept(hat.get()));
            }
        });
        MinecraftForge.EVENT_BUS.addListener(CyberHats::onInteract);
        MinecraftForge.EVENT_BUS.addListener(CyberHats::dropHat);
        if (FMLEnvironment.dist == Dist.CLIENT) {
            CyberHatsClient.init(modBus);
        }
    }

    public static ResourceLocation id(String path) {
        return new ResourceLocation(MODID, path);
    }

    /** Before the drone's own right click (a Taxi ride, a pickup), so it works on any drone. */
    private static void onInteract(PlayerInteractEvent.EntityInteract event) {
        if (event.getTarget() instanceof DroneEntity drone && dressDrone(event.getEntity(), drone, event.getHand())) {
            event.setCancellationResult(InteractionResult.sidedSuccess(event.getLevel().isClientSide));
            event.setCanceled(true);
        }
    }

    /** A hat in hand goes on a bare drone, shears take its hat off. Whether the click did either. */
    static boolean dressDrone(Player player, DroneEntity drone, InteractionHand hand) {
        ItemStack held = player.getItemInHand(hand);
        ItemStack worn = drone.getItemBySlot(EquipmentSlot.HEAD);
        if (held.getItem() instanceof HatItem && worn.isEmpty()) {
            if (!drone.level().isClientSide) {
                drone.setItemSlot(EquipmentSlot.HEAD, held.split(1));
                // Dropped whole when the drone dies or is picked up
                drone.setGuaranteedDrop(EquipmentSlot.HEAD);
                drone.level().playSound(null, drone, SoundEvents.ARMOR_EQUIP_LEATHER, SoundSource.NEUTRAL, 1.0F, 1.0F);
            }
            return true;
        }
        if (held.getItem() instanceof ShearsItem && worn.getItem() instanceof HatItem) {
            if (!drone.level().isClientSide) {
                drone.setItemSlot(EquipmentSlot.HEAD, ItemStack.EMPTY);
                drone.spawnAtLocation(worn, 1.0F);
                held.hurtAndBreak(1, player, user -> user.broadcastBreakEvent(hand));
                drone.level().playSound(null, drone, SoundEvents.SHEEP_SHEAR, SoundSource.NEUTRAL, 1.0F, 1.0F);
            }
            return true;
        }
        return false;
    }

    /** A picked-up drone turns into an item, which cannot carry the hat: it falls where the drone was. */
    private static void dropHat(EntityLeaveLevelEvent event) {
        if (event.getEntity() instanceof DroneEntity drone && event.getLevel() instanceof ServerLevel
                && drone.getRemovalReason() == Entity.RemovalReason.DISCARDED) {
            ItemStack hat = drone.getItemBySlot(EquipmentSlot.HEAD);
            if (!hat.isEmpty()) {
                drone.setItemSlot(EquipmentSlot.HEAD, ItemStack.EMPTY);
                drone.spawnAtLocation(hat);
            }
        }
    }
}
