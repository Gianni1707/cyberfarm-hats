package com.cyberhats;

import com.cyberfarm.entity.DroneEntity;
import com.cyberfarm.registry.ModEntities;

import net.minecraft.core.BlockPos;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.ItemStack;
import net.minecraftforge.gametest.GameTestHolder;
import net.minecraftforge.gametest.PrefixGameTestTemplate;

@GameTestHolder(CyberHats.MODID)
@PrefixGameTestTemplate(false)
public class HatTests {
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
