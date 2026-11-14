package com.cyberhats;

import com.cyberfarm.entity.DroneEntity;
import com.cyberfarm.registry.ModEntities;

import net.minecraft.core.BlockPos;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.InventoryMenu;
import net.minecraft.world.inventory.Slot;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraftforge.gametest.GameTestHolder;
import net.minecraftforge.gametest.PrefixGameTestTemplate;

@GameTestHolder(CyberHats.MODID)
@PrefixGameTestTemplate(false)
public class HatTests {
    /**
     * The player's menu has the Hat slot after every vanilla slot; it takes only hats, kept on the player. With Curios
     * or Cosmetic Armor there is no such slot at all.
     */
    @GameTest(template = "empty")
    public static void hatSlot(GameTestHelper helper) {
        Player player = helper.makeMockPlayer();
        if (!HatSlot.ownSlot()) {
            helper.assertTrue(player.inventoryMenu.slots.size() == InventoryMenu.SHIELD_SLOT + 1, "with a cosmetic slot mod, no Hat slot");
            helper.succeed();
            return;
        }
        Slot slot = player.inventoryMenu.getSlot(InventoryMenu.SHIELD_SLOT + 1);
        helper.assertTrue(slot instanceof HatSlot.Holder, "the Hat slot follows the offhand");
        ItemStack hat = new ItemStack(CyberHats.HATS.get(0).get());
        helper.assertTrue(slot.mayPlace(hat), "a hat goes in");
        helper.assertFalse(slot.mayPlace(new ItemStack(Items.IRON_HELMET)), "a helmet does not");
        slot.set(hat);
        helper.assertTrue(HatSlot.worn(player).hat().is(hat.getItem()) && !HatSlot.shownHat(player).isEmpty(), "the player wears it, shown");
        HatSlot.setWorn(player, new HatSlot.Worn(hat, false));
        helper.assertTrue(HatSlot.shownHat(player).isEmpty() && slot.getItem().is(hat.getItem()), "hidden, it stays in the slot");
        helper.succeed();
    }

    /** A right click puts the hat on the drone, and a picked-up drone drops it. */
    @GameTest(template = "empty")
    public static void droneHat(GameTestHelper helper) {
        ItemStack hat = new ItemStack(CyberHats.HATS.get(0).get());
        DroneEntity drone = helper.spawnWithNoFreeWill(ModEntities.DRONE.get(), 0, 1, 0);
        Player player = helper.makeMockPlayer();
        player.setItemInHand(InteractionHand.MAIN_HAND, hat.copy());
        helper.assertTrue(CyberHats.dressDrone(player, drone, InteractionHand.MAIN_HAND), "a hat goes on a drone");
        helper.assertTrue(drone.getItemBySlot(EquipmentSlot.HEAD).is(hat.getItem()), "the drone wears it");
        drone.discard();
        helper.assertItemEntityPresent(hat.getItem(), new BlockPos(0, 1, 0), 2.0);
        helper.succeed();
    }
}
