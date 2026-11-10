package com.cyberhats;

import java.util.List;
import java.util.Set;
import java.util.function.Consumer;
import java.util.stream.Stream;

import com.cyberfarm.entity.DroneEntity;
import com.cyberfarm.registry.ModCreativeTabs;
import com.cyberfarm.registry.ModEntities;

import net.minecraft.ChatFormatting;
import net.minecraft.core.BlockPos;
import net.minecraft.core.component.DataComponents;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.core.registries.Registries;
import net.minecraft.gametest.framework.FunctionGameTestInstance;
import net.minecraft.network.chat.Component;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.gametest.framework.TestData;
import net.minecraft.resources.Identifier;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.tags.TagKey;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.component.ItemLore;
import net.minecraft.world.item.equipment.Equippable;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.fml.common.Mod;
import net.neoforged.neoforge.common.NeoForge;
import net.neoforged.neoforge.event.BuildCreativeModeTabContentsEvent;
import net.neoforged.neoforge.event.RegisterGameTestsEvent;
import net.neoforged.neoforge.event.entity.EntityLeaveLevelEvent;
import net.neoforged.neoforge.registries.DeferredHolder;
import net.neoforged.neoforge.registries.DeferredItem;
import net.neoforged.neoforge.registries.DeferredRegister;

/**
 * Hats for players and CyberFarm drones. A hat is a plain item with vanilla's equippable component: worn in the
 * head slot, put on a drone with a right click and taken off it with shears, the way a saddle goes on a horse.
 * Vanilla draws it on the player; {@link CyberHatsClient} draws it on the drone.
 */
@Mod(CyberHats.MODID)
public class CyberHats {
    public static final String MODID = "cyberhats";

    /** Who can wear a hat. Vanilla draws head items only on mobs with a humanoid head, so add others with care. */
    private static final TagKey<EntityType<?>> HAT_WEARERS = TagKey.create(Registries.ENTITY_TYPE, id("hat_wearers"));

    private static final DeferredRegister.Items ITEMS = DeferredRegister.createItems(MODID);
    /** The hats from a game, anime or film: each shows a famous line from it, item.cyberhats.<name>.quote (tools/hats.py). */
    private static final Set<String> QUOTED = Set.of(
            "red_plumber_cap", "green_plumber_cap", "mushroom_cap", "elf_cap", "straw_hat", "cowboy_hat", "baseball_cap",
            "flat_cap", "fedora", "fez", "party_hat", "halo", "chicken_hat", "professor_top_hat", "apprentice_cap",
            "phantom_thief_hat", "trainer_cap", "black_mage_hat");
    /** Every hat. A new one needs its name here and its boxes in tools/hats.py, which writes all its files. */
    public static final List<DeferredItem<Item>> HATS = Stream.of(
            "hard_hat", "wizard_hat", "flat_cap", "straw_hat", "elf_cap", "cowboy_hat", "baseball_cap", "top_hat", "goggle_top_hat",
            "red_plumber_cap", "green_plumber_cap", "chef_hat", "crown", "santa_hat", "viking_helmet", "propeller_beanie",
            "pirate_hat", "sombrero", "fedora", "beret", "ushanka", "graduation_cap", "jester_hat", "party_hat", "witch_hat",
            "fez", "mushroom_cap", "halo", "samurai_helmet", "aviator_cap", "captain_hat", "frog_hat", "chicken_hat",
            "professor_top_hat", "time_traveler_top_hat", "phantom_thief_hat", "apprentice_cap", "trainer_cap", "wanderer_hat",
            "black_mage_hat")
            .map(CyberHats::hat).toList();

    private static final DeferredRegister<Consumer<GameTestHelper>> TESTS = DeferredRegister.create(Registries.TEST_FUNCTION, MODID);
    private static final DeferredHolder<Consumer<GameTestHelper>, Consumer<GameTestHelper>> DRONE_HAT_TEST =
            TESTS.register("drone_hat", () -> CyberHats::testDroneHat);

    public CyberHats(IEventBus modBus) {
        ITEMS.register(modBus);
        TESTS.register(modBus);
        modBus.addListener((BuildCreativeModeTabContentsEvent event) -> {
            if (event.getTabKey() == ModCreativeTabs.MAIN.getKey()) {
                HATS.forEach(event::accept);
            }
        });
        modBus.addListener((RegisterGameTestsEvent event) -> event.registerTest(id("drone_hat"), new FunctionGameTestInstance(
                DRONE_HAT_TEST.getKey(),
                new TestData<>(event.registerEnvironment(id("default")), Identifier.withDefaultNamespace("empty"), 20, 0, true))));
        NeoForge.EVENT_BUS.addListener(CyberHats::dropHat);
    }

    public static Identifier id(String path) {
        return Identifier.fromNamespaceAndPath(MODID, path);
    }

    private static DeferredItem<Item> hat(String name) {
        return ITEMS.registerSimpleItem(name, properties -> {
            properties.stacksTo(1).component(DataComponents.EQUIPPABLE,
                    // No equipment asset: vanilla then draws the item's own model on the wearer's head
                    Equippable.builder(EquipmentSlot.HEAD)
                            .setEquipSound(SoundEvents.ARMOR_EQUIP_LEATHER)
                            .setAllowedEntities(BuiltInRegistries.acquireBootstrapRegistrationLookup(BuiltInRegistries.ENTITY_TYPE).getOrThrow(HAT_WEARERS))
                            .setEquipOnInteract(true)
                            .setCanBeSheared(true)
                            .build());
            if (QUOTED.contains(name)) {
                properties.component(DataComponents.LORE,
                        new ItemLore(List.of(Component.translatable("item.cyberhats." + name + ".quote").withStyle(ChatFormatting.GRAY))));
            }
            return properties;
        });
    }

    /** A picked-up drone turns into an item, which cannot carry the hat: it falls where the drone was. */
    private static void dropHat(EntityLeaveLevelEvent event) {
        if (event.getEntity() instanceof DroneEntity drone && event.getLevel() instanceof ServerLevel level
                && drone.getRemovalReason() == Entity.RemovalReason.DISCARDED) {
            drone.dropPreservedEquipment(level);
        }
    }

    private static void testDroneHat(GameTestHelper helper) {
        ItemStack hat = HATS.getFirst().toStack();
        DroneEntity drone = helper.spawnWithNoFreeWill(ModEntities.DRONE.get(), 0, 1, 0);
        helper.assertTrue(drone.isEquippableInSlot(hat, EquipmentSlot.HEAD), "a drone can wear a hat");
        helper.assertFalse(helper.spawnWithNoFreeWill(EntityType.COW, 0, 1, 0).isEquippableInSlot(hat, EquipmentSlot.HEAD), "a cow cannot");
        // What a right click with the hat does
        drone.setItemSlot(EquipmentSlot.HEAD, hat);
        drone.setGuaranteedDrop(EquipmentSlot.HEAD);
        drone.discard();
        helper.assertItemEntityPresent(hat.getItem(), new BlockPos(0, 1, 0), 2.0);
        helper.succeed();
    }
}
