package com.cyberhats.mixin;

import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

import com.cyberhats.HatSlot;

import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.InventoryMenu;

/**
 * Adds the Hat slot after the offhand's, so every vanilla slot keeps its index. Both sides build the player's menu the
 * same way, so they agree on it; with Curios or Cosmetic Armor installed neither adds it.
 */
@Mixin(InventoryMenu.class)
public abstract class InventoryMenuMixin {
    @Inject(method = "<init>", at = @At("TAIL"))
    private void cyberhats$addHatSlot(Inventory inventory, boolean active, Player owner, CallbackInfo info) {
        if (HatSlot.ownSlot()) {
            ((AbstractContainerMenuAccessor) this).cyberhats$addSlot(HatSlot.slot(owner));
        }
    }
}
