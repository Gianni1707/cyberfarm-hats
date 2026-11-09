package com.cyberhats;

import mezz.jei.api.IModPlugin;
import mezz.jei.api.JeiPlugin;
import mezz.jei.api.registration.IRecipeRegistration;

import net.minecraft.network.chat.Component;
import net.minecraft.resources.Identifier;
import net.neoforged.neoforge.registries.DeferredItem;

/** JEI's information page on every hat: how to wear it, and how a drone wears it. Loaded by JEI only when present. */
@JeiPlugin
public class CyberHatsJeiPlugin implements IModPlugin {
    @Override
    public Identifier getPluginUid() {
        return CyberHats.id("jei");
    }

    @Override
    public void registerRecipes(IRecipeRegistration registration) {
        registration.addItemStackInfo(CyberHats.HATS.stream().map(DeferredItem::toStack).toList(), Component.translatable("cyberhats.jei.hat"));
    }
}
