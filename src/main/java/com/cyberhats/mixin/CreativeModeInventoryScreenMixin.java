package com.cyberhats.mixin;

import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.ModifyArg;

import com.cyberhats.HatSlot;

import net.minecraft.client.gui.screens.inventory.CreativeModeInventoryScreen;
import net.minecraft.world.inventory.Slot;

/** The creative inventory places the player's slots by their number, which would put the Hat slot on the hotbar. */
@Mixin(CreativeModeInventoryScreen.class)
public abstract class CreativeModeInventoryScreenMixin {
    private static final String WRAPPER =
            "Lnet/minecraft/client/gui/screens/inventory/CreativeModeInventoryScreen$SlotWrapper;<init>(Lnet/minecraft/world/inventory/Slot;III)V";

    @ModifyArg(method = "selectTab", at = @At(value = "INVOKE", target = WRAPPER), index = 2)
    private int cyberhats$hatSlotX(Slot target, int index, int x, int y) {
        return target instanceof HatSlot.Holder ? HatSlot.CREATIVE_X : x;
    }

    @ModifyArg(method = "selectTab", at = @At(value = "INVOKE", target = WRAPPER), index = 3)
    private int cyberhats$hatSlotY(Slot target, int index, int x, int y) {
        return target instanceof HatSlot.Holder ? HatSlot.CREATIVE_Y : y;
    }
}
