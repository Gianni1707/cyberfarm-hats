package com.cyberhats.mixin;

import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Invoker;

import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.inventory.Slot;

@Mixin(AbstractContainerMenu.class)
public interface AbstractContainerMenuAccessor {
    @Invoker("addSlot")
    Slot cyberhats$addSlot(Slot slot);
}
