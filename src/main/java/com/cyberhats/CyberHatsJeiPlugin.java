package com.cyberhats;

import mezz.jei.api.IModPlugin;
import mezz.jei.api.JeiPlugin;
import mezz.jei.api.constants.VanillaTypes;
import mezz.jei.api.registration.IRecipeRegistration;

import net.minecraft.network.chat.Component;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.item.ItemStack;

/** JEI's information page on every hat: how to wear it, and how a drone wears it. Loaded by JEI only when present. */
@JeiPlugin
public class CyberHatsJeiPlugin implements IModPlugin {
    @Override
    public ResourceLocation getPluginUid() {
        return CyberHats.id("jei");
    }

    @Override
    public void registerRecipes(IRecipeRegistration registration) {
        registration.addIngredientInfo(CyberHats.HATS.stream().map(hat -> new ItemStack(hat.get())).toList(), VanillaTypes.ITEM_STACK,
                Component.translatable("cyberhats.jei.hat"));
    }
}
